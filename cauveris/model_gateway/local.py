"""
Local model gateway: a real client for a locally served model.

Cauveris has to keep working when the cloud provider is unreachable - on a
robotics test bench with no egress, during an incident that is *caused* by
the network, or on a laptop where nobody has configured an API key.  That is
what this gateway is for: it talks to a model that runs on the machine.

Two kinds of server speak the OpenAI chat-completions protocol, and both are
supported because both are common on edge hardware:

* **Ollama** - ``http://localhost:11434/v1``
* **vLLM / SGLang / LM Studio** - ``http://localhost:8000/v1``

The endpoints are configured, not guessed, and each one is *probed* before it
is used, so a configured-but-dead server costs one cheap request rather than
a timeout inside the caller's latency budget.

When no local model answers, this gateway says so plainly.  It does not
invent an analysis: a fabricated root cause is worse than no root cause,
because it is indistinguishable from a real one once it is in a report.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Type

import httpx
from pydantic import BaseModel

from cauveris.config import get_settings
from .base import ModelGateway, ModelResponse, extract_json_from_text

logger = logging.getLogger(__name__)

__all__ = ["LocalModelGateway", "NoLocalModelAvailable"]


class NoLocalModelAvailable(Exception):
    """No local model server answered on any configured endpoint."""

    def __init__(self, attempts: List[Dict[str, Any]]):
        self.attempts = attempts
        detail = "; ".join(
            f"{a['endpoint']}: {a['error']}" for a in attempts
        ) or "no endpoints configured"
        super().__init__(f"No local model available ({detail})")


class LocalModelGateway(ModelGateway):
    """
    A gateway that serves prompts from a model running on the local machine.

    The gateway is "available" when it has been given at least one endpoint
    to try - whether a server is actually listening there is a question
    answered per request, because a server that was up a minute ago can be
    down now and the answer has to be true *now*.
    """

    def __init__(
        self,
        endpoints: Optional[List[str]] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
        probe_timeout: Optional[float] = None,
    ):
        self.settings = get_settings()
        if endpoints is None:
            configured = getattr(self.settings, "local_model_endpoints", "") or ""
            endpoints = [
                part.strip().rstrip("/")
                for part in str(configured).split(",")
                if part.strip()
            ]
        self.endpoints: List[str] = endpoints
        self.model_name: str = str(
            model_name
            or getattr(self.settings, "local_model_name", "qwen2.5:7b-instruct")
            or "qwen2.5:7b-instruct"
        )
        self.timeout = float(
            timeout
            if timeout is not None
            else getattr(self.settings, "local_model_timeout_seconds", 60.0)
        )
        self.probe_timeout = float(
            probe_timeout
            if probe_timeout is not None
            else getattr(self.settings, "local_model_probe_timeout_seconds", 0.5)
        )
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ API

    def is_available(self) -> bool:
        """Whether there is anywhere to look for a local model."""
        return bool(self.endpoints)

    async def generate(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ModelResponse:
        """
        Send the prompt to the first local server that answers.

        Raises:
            NoLocalModelAvailable: when no configured endpoint served the
                request.  The exception carries the per-endpoint reasons.
        """
        attempts: List[Dict[str, Any]] = []
        for endpoint in self.endpoints:
            started = time.perf_counter()
            try:
                response = await self._complete(
                    endpoint, prompt, schema, temperature, max_tokens
                )
            except Exception as exc:
                elapsed = (time.perf_counter() - started) * 1000.0
                attempts.append(
                    {
                        "endpoint": endpoint,
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_ms": round(elapsed, 2),
                    }
                )
                logger.info("Local model endpoint %s did not answer: %s", endpoint, exc)
                continue

            attempts.append(
                {
                    "endpoint": endpoint,
                    "error": None,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
                }
            )
            response.usage = {**(response.usage or {}), "provider_attempts": attempts}
            response.endpoint = endpoint
            return response

        raise NoLocalModelAvailable(attempts)

    async def aclose(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def probe(self) -> List[Dict[str, Any]]:
        """
        What each configured endpoint is doing, right now.

        The result is a fact about the machine, measured rather than
        assumed: an endpoint that answers is reported with the models it
        serves, and an endpoint that does not is reported with the error it
        gave.

        The endpoints are probed concurrently.  A dead endpoint costs a
        connect timeout, and doing that one after the other makes the check
        as slow as the sum of the dead ones - which is exactly when an
        operator is waiting for the check to come back.
        """

        async def probe_one(endpoint: str) -> Dict[str, Any]:
            started = time.perf_counter()
            models, error = await self._list_models(endpoint)
            elapsed = round((time.perf_counter() - started) * 1000.0, 1)
            if models:
                return {
                    "endpoint": endpoint,
                    "reachable": True,
                    "latency_ms": elapsed,
                    "models": models,
                }
            return {
                "endpoint": endpoint,
                "reachable": False,
                "latency_ms": elapsed,
                "models": [],
                "error": error or "no models served at this endpoint",
            }

        if not self.endpoints:
            return []
        return list(await asyncio.gather(*(probe_one(e) for e in self.endpoints)))

    # ------------------------------------------------------------ internals

    async def _get_client(self) -> httpx.AsyncClient:
        """A client that does not follow redirects or inherit a proxy."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=False,
                trust_env=False,
            )
        return self._client

    async def _list_models(self, endpoint: str) -> Tuple[List[str], Optional[str]]:
        """
        The models a server actually serves, and why not when it serves none.

        Asking is the only way to know: a fixed model name is wrong as soon
        as somebody pulls a different image, and a wrong name turns into a
        404 on every request.

        Returns:
            ``(models, error)``.  The error is ``None`` when the server
            answered with a model list, and a description of what went wrong
            otherwise.
        """
        client = await self._get_client()
        try:
            response = await client.get(
                f"{endpoint}/models",
                timeout=self.probe_timeout,
            )
            if response.status_code != 200:
                return [], f"HTTP {response.status_code}"
            payload = response.json()
        except Exception as exc:
            logger.debug("Local model probe of %s failed: %s", endpoint, exc)
            return [], f"{type(exc).__name__}: {exc}"

        entries = payload.get("data", payload.get("models", []))
        models: List[str] = []
        for entry in entries:
            if isinstance(entry, str):
                models.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("id") or entry.get("name")
                if name:
                    models.append(str(name))
        if not models:
            return [], "the server served no models"
        return models, None

    def _choose_model(self, available: List[str]) -> Tuple[str, bool]:
        """
        The model to request, and whether the choice was an exact match.

        The configured name wins when the server serves it.  Otherwise the
        server's own list decides - preferring the configured name as a
        prefix, because ``qwen2.5:7b-instruct`` should match
        ``qwen2.5:7b-instruct-q4_K_M`` before it matches an unrelated model.
        """
        if not available:
            return self.model_name, False
        if self.model_name in available:
            return self.model_name, True
        prefixed = [m for m in available if m.startswith(self.model_name)]
        if prefixed:
            return prefixed[0], True
        return available[0], False

    async def _complete(
        self,
        endpoint: str,
        prompt: str,
        schema: Optional[Type[BaseModel]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> ModelResponse:
        """One chat-completions round trip against one server."""
        available, probe_error = await self._list_models(endpoint)
        model, exact = self._choose_model(available)
        if probe_error and not available:
            logger.debug("Local server %s served no models: %s", endpoint, probe_error)
        if not exact:
            logger.info(
                "Local server at %s does not serve %s exactly; requesting %s",
                endpoint,
                self.model_name,
                model,
            )

        messages: List[Dict[str, str]] = []
        if schema is not None:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "You are an expert root cause analysis and systems "
                        "engineering AI. Respond ONLY with a valid JSON object "
                        "matching this schema. No preamble, no markdown "
                        "fences, no commentary.\n"
                        + json.dumps(schema.model_json_schema(), indent=2)
                    ),
                }
            )
        messages.append({"role": "user", "content": prompt})

        body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        client = await self._get_client()
        response = await client.post(
            f"{endpoint}/chat/completions",
            json=body,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{endpoint} returned {response.status_code}",
                request=response.request,
                response=response,
            )

        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError(f"{endpoint} returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content is None:
            # Some servers put the answer under "text" instead.
            content = choices[0].get("text")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"{endpoint} returned an empty completion")

        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(
            usage.get("total_tokens", prompt_tokens + completion_tokens) or 0
        )
        structured = extract_json_from_text(content) if schema is not None else None

        return ModelResponse(
            content=content,
            structured_data=structured,
            model_used=str(payload.get("model") or model),
            provider="local-llm",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            cost=0.0,
            inference=True,
            endpoint=endpoint,
        )

"""
Nebius model gateway provider.
Calls real Nebius Token Factory APIs when credentials are available.
"""

from typing import Any, Dict, List, Optional, Type
import json
import logging
import httpx
from pydantic import BaseModel
from .base import ModelGateway, ModelResponse, extract_json_from_text
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


class CredentialNotConfigured(Exception):
    """Raised when Nebius credentials are not configured."""

    pass


def normalize_nebius_url(url: Optional[str]) -> str:
    """Normalize Nebius base URL to a live endpoint, replacing dead domains."""
    if not url:
        return "https://api.tokenfactory.nebius.com/v1"
    clean = url.strip().rstrip("/")
    if "api.nebius.ai" in clean:
        clean = clean.replace("api.nebius.ai", "api.tokenfactory.nebius.com")
    return clean


class NebiusModelGateway(ModelGateway):
    """Nebius model gateway that calls real APIs with dynamic model resolution and fallbacks."""

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        timeout: Optional[float] = None,
    ):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = client
        self._resolved_model: Optional[str] = None
        self._cached_available_models: Optional[List[str]] = None
        # A health check needs a short leash; a reasoning call needs a long
        # one.  The caller decides.
        self.timeout = float(
            timeout if timeout is not None
            else getattr(self.settings, "nebius_timeout_seconds", 60.0)
        )

    def is_available(self) -> bool:
        """Check if Nebius credentials are configured."""
        return bool(self.settings.nebius_api_key)

    def _get_base_url(self) -> str:
        """Get the validated and normalized base URL."""
        return normalize_nebius_url(self.settings.nebius_base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        base_url = self._get_base_url()
        if self._client is None or str(self._client.base_url).rstrip("/") != base_url.rstrip("/"):
            if self._client is not None:
                await self._client.aclose()
            self._client = httpx.AsyncClient(
                base_url=base_url,
                headers={
                    "Authorization": f"Bearer {self.settings.nebius_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Cauveris-ModelGateway/1.0",
                },
                timeout=self.timeout,
            )
        return self._client

    async def _get_available_models(self, client: httpx.AsyncClient) -> List[str]:
        """Fetch models actually available on the Nebius account."""
        if self._cached_available_models is not None:
            return self._cached_available_models

        try:
            resp = await client.get("/models")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                if models:
                    self._cached_available_models = models
                    return models
        except Exception as e:
            logger.debug(f"Unable to query /models: {e}")

        return []

    async def _resolve_model(self, client: httpx.AsyncClient, requested_model: Optional[str] = None) -> str:
        """
        Resolve requested model name against actual models available in the Nebius Token Factory account.
        If a fictional placeholder is used (e.g. nemotron-3-super), pick the best active model from /models.
        """
        if self._resolved_model and not requested_model:
            return self._resolved_model

        model_name = requested_model or self.settings.model_reasoning
        fictional_placeholders = {"nemotron-3-nano", "nemotron-3-super", "nemotron-3-ultra"}

        # If it's a real model ID provided by user and not a placeholder, verify or use directly
        if model_name and model_name not in fictional_placeholders and "/" in model_name:
            self._resolved_model = model_name
            return model_name

        available_models = await self._get_available_models(client)
        if available_models:
            # If the requested name matches an available model, use it
            if model_name in available_models:
                self._resolved_model = model_name
                return model_name

            # Look for Nemotron models first if requested
            if "nemotron" in (model_name or "").lower():
                nemotrons = [m for m in available_models if "nemotron" in m.lower()]
                if nemotrons:
                    self._resolved_model = nemotrons[0]
                    return nemotrons[0]

            # Look for Llama 3.1 70B
            llamas_70b = [m for m in available_models if "llama-3.1-70b" in m.lower() or "llama-3-70b" in m.lower()]
            if llamas_70b:
                self._resolved_model = llamas_70b[0]
                return llamas_70b[0]

            # Look for other Llama 3.1 models
            llamas = [m for m in available_models if "llama" in m.lower()]
            if llamas:
                self._resolved_model = llamas[0]
                return llamas[0]

            # Look for DeepSeek
            deepseeks = [m for m in available_models if "deepseek" in m.lower()]
            if deepseeks:
                self._resolved_model = deepseeks[0]
                return deepseeks[0]

            # Look for Qwen
            qwens = [m for m in available_models if "qwen" in m.lower()]
            if qwens:
                self._resolved_model = qwens[0]
                return qwens[0]

            # Default to first active model on account
            self._resolved_model = available_models[0]
            return available_models[0]

        # Standard default fallback
        fallback = "meta-llama/Meta-Llama-3.1-70B-Instruct"
        self._resolved_model = fallback
        return fallback

    async def generate(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ModelResponse:
        """
        Generate a response using Nebius Token Factory.

        Args:
            prompt: The input prompt
            schema: Optional Pydantic schema for structured output
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            ModelResponse with content and optionally structured data

        Raises:
            CredentialNotConfigured: If Nebius credentials are not set
        """
        if not self.is_available():
            raise CredentialNotConfigured(
                "Nebius API credentials not configured. "
                "Set NEBIUS_API_KEY environment variable. "
                "Optional: NEBIUS_BASE_URL (defaults to https://api.tokenfactory.nebius.com/v1)"
            )

        client = await self._get_client()
        model_to_use = await self._resolve_model(client, self.settings.model_reasoning)

        # Build messages
        messages = []
        if schema is not None:
            schema_json = json.dumps(schema.model_json_schema(), indent=2)
            system_msg = (
                "You are an expert root cause analysis and systems engineering AI.\n"
                "Analyze the provided system telemetry, incident events, and latency metrics.\n"
                "You MUST respond ONLY with a valid JSON object matching the following schema:\n"
                f"{schema_json}\n"
                "Do NOT include conversational preamble, markdown backticks, or trailing commentary. Only output raw JSON."
            )
            messages.append({"role": "system", "content": system_msg})

        messages.append({"role": "user", "content": prompt})

        request_body: Dict[str, Any] = {
            "model": model_to_use,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens is not None:
            request_body["max_tokens"] = max_tokens
        elif schema is not None:
            request_body["max_tokens"] = 2048

        # When schema is requested, attempt json_object mode (OpenAI standard)
        if schema is not None:
            request_body["response_format"] = {"type": "json_object"}

        response = None
        try:
            response = await client.post("/chat/completions", json=request_body)
            # If server doesn't support response_format (e.g. strict vLLM without json mode)
            if response.status_code == 400 and "response_format" in response.text:
                request_body.pop("response_format", None)
                response = await client.post("/chat/completions", json=request_body)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # If 404 (model not found), invalidate cache, try resolving again, and retry once
            if e.response.status_code == 404:
                self._cached_available_models = None
                self._resolved_model = None
                alt_model = await self._resolve_model(client, None)
                if alt_model and alt_model != model_to_use:
                    request_body["model"] = alt_model
                    response = await client.post("/chat/completions", json=request_body)
                    response.raise_for_status()
                    model_to_use = alt_model
                else:
                    logger.error(f"Nebius API model not found: {model_to_use} ({e.response.text})")
                    raise
            else:
                logger.error(f"Nebius API error: {e.response.status_code} - {e.response.text}")
                raise
        except Exception as e:
            logger.error(f"Error calling Nebius API: {e}")
            raise

        result = response.json()

        # Extract content
        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {}) or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(
            usage.get("total_tokens", prompt_tokens + completion_tokens) or 0
        )

        # Try to parse structured data if schema was provided
        structured_data = None
        if schema is not None:
            structured_data = extract_json_from_text(content)

        return ModelResponse(
            content=content,
            structured_data=structured_data,
            model_used=result.get("model", model_to_use),
            provider="nebius",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            cost=self._estimate_cost(
                {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                model_to_use,
            ),
            inference=True,
        )

    def _estimate_cost(self, usage: Dict[str, Any], model: str) -> float:
        """Estimate cost based on token usage."""
        rates_per_1k_tokens = {
            "meta-llama/Meta-Llama-3.1-8B-Instruct": 0.0001,
            "meta-llama/Meta-Llama-3.1-70B-Instruct": 0.0007,
            "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF": 0.0007,
            "deepseek-ai/DeepSeek-V3": 0.0005,
            "deepseek-ai/DeepSeek-R1": 0.0015,
        }

        rate = rates_per_1k_tokens.get(model, 0.0005)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = prompt_tokens + completion_tokens

        return (total_tokens / 1000) * rate

    async def aclose(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def probe(self) -> Dict[str, Any]:
        """
        What the hosted provider is doing, right now.

        The same contract as the local gateway's probe: a measured fact
        about the endpoint, not an assumption about the configuration.
        """
        import time

        started = time.perf_counter()
        base_url = self._get_base_url()
        if not self.is_available():
            return {
                "endpoint": base_url,
                "reachable": False,
                "latency_ms": None,
                "models": [],
                "error": "no API key configured",
            }
        try:
            client = await self._get_client()
            models = await self._get_available_models(client)
        except Exception as exc:
            return {
                "endpoint": base_url,
                "reachable": False,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "models": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        if models:
            return {
                "endpoint": base_url,
                "reachable": True,
                "latency_ms": elapsed,
                "models": models,
            }
        return {
            "endpoint": base_url,
            "reachable": False,
            "latency_ms": elapsed,
            "models": [],
            "error": "the provider served no model list",
        }

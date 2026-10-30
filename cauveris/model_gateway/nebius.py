"""
Nebius model gateway provider and NVIDIA model integration.
Calls real Nebius Token Factory APIs when credentials are available.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Type

import httpx
from pydantic import BaseModel

from cauveris.config import get_settings
from .base import ModelGateway, ModelResponse, extract_json_from_text
from .circuit_breaker import (
    get_controller,
)
from .enums import ModelTaskType, ProviderState, ValidationResult
from .records import ModelExecutionRecord, get_execution_store
from .security import redact_secrets, wrap_untrusted_input
from .tasks import TASK_REGISTRY

logger = logging.getLogger(__name__)


class CredentialNotConfigured(Exception):
    """Raised when Nebius credentials are not configured."""
    pass


class ModelRateLimitedError(Exception):
    """Raised when Nebius responds with 429 Too Many Requests."""
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
    """
    Nebius model gateway providing robust access to hosted NVIDIA open-source models.
    Supports bounded tasks, secret scrubbing, prompt protection, and execution auditing.
    """

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = client
        self._resolved_model: Optional[str] = None
        self._cached_available_models: Optional[List[str]] = None
        self.timeout = float(
            timeout if timeout is not None
            else getattr(self.settings, "nebius_request_timeout_seconds", 60.0)
        )
        self.controller = get_controller()
        self.provider_id = "nebius"
        self.model_id = self.settings.nebius_model_id or "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"

    def is_available(self) -> bool:
        """Check if Nebius credentials and provider are active."""
        return bool(self.settings.nebius_api_key and self.settings.nebius_enabled)

    def get_provider_state(self) -> ProviderState:
        """Current operational state of Nebius provider."""
        if not self.settings.nebius_api_key:
            return ProviderState.LOCAL_DETERMINISTIC_ONLY
        if not self.settings.nebius_base_url or not self.settings.nebius_base_url.startswith(("http://", "https://")):
            return ProviderState.CONFIGURATION_INVALID
        if self.controller.state == "OPEN":
            return ProviderState.PROVIDER_UNAVAILABLE
        return ProviderState.NEBIUS_NVIDIA_ACTIVE

    def _get_base_url(self) -> str:
        """Get the validated and normalized base URL."""
        return normalize_nebius_url(self.settings.nebius_base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is not None:
            return self._client
        base_url = self._get_base_url()
        headers = {
            "Authorization": f"Bearer {self.settings.nebius_api_key or ''}",
            "Content-Type": "application/json",
            "User-Agent": "Cauveris-ModelGateway/1.0",
        }
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
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

    async def resolve_model(self, client: httpx.AsyncClient, requested_model: Optional[str] = None) -> str:
        """
        Resolve requested model name against configured NVIDIA model or account models.
        """
        if self._resolved_model and not requested_model:
            return self._resolved_model

        fictional_placeholders = {"nemotron-3-nano", "nemotron-3-super", "nemotron-3-ultra"}
        model_name = (
            requested_model
            or (self.settings.model_reasoning if self.settings.model_reasoning and self.settings.model_reasoning != "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF" else None)
            or self.settings.nebius_model_id
            or self.settings.model_reasoning
            or "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"
        )

        available_models = await self._get_available_models(client)
        if available_models:
            # 1. Exact match
            if model_name in available_models:
                self._resolved_model = model_name
                return model_name

            # 2. Look for NVIDIA Nemotron models, prioritizing Lightning
            if "nemotron" in (model_name or "").lower():
                nemotrons = (
                    [m for m in available_models if "lightning" in m.lower()]
                    or [m for m in available_models if "nemotron" in m.lower()]
                )
                if nemotrons:
                    self._resolved_model = nemotrons[0]
                    return nemotrons[0]

            # 3. Look for Llama 3.1 70B
            llamas = [m for m in available_models if "llama-3.1-70b" in m.lower()]
            if llamas:
                self._resolved_model = llamas[0]
                return llamas[0]

            self._resolved_model = available_models[0]
            return available_models[0]

        # If it's a real model ID specified by user and not a fictional placeholder, use it
        if model_name and "/" in model_name and model_name not in fictional_placeholders:
            self._resolved_model = model_name
            return model_name

        default_model = self.settings.nebius_model_id or "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"
        self._resolved_model = default_model
        return default_model

    _resolve_model = resolve_model

    async def generate(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        incident_id: str = "global",
        job_id: Optional[str] = None,
        task_id: str = "GENERIC_REASONING",
        **kwargs: Any,
    ) -> ModelResponse:
        """
        Generate response from Nebius NVIDIA endpoint with full guardrails.
        """
        if not self.is_available():
            raise CredentialNotConfigured("Nebius API credentials not configured.")

        # Check circuit breaker and budget
        self.controller.check_can_execute()

        # Sanitize prompt of all credentials and secrets
        redacted_prompt, redaction_count = redact_secrets(prompt)

        # Check cache if explicitly requested or for registered bounded tasks
        should_cache = kwargs.get("use_cache", task_id != "GENERIC_REASONING")
        cache_key = self.controller.compute_hash(f"{incident_id}:{task_id}", redacted_prompt)
        if should_cache:
            cached_result = self.controller.get_cached(cache_key)
            if cached_result:
                logger.info("Returning cached model response for hash %s", cache_key[:12])
                return ModelResponse(**cached_result)

        client = await self._get_client()
        model_to_use = await self.resolve_model(client)

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

        messages.append({"role": "user", "content": redacted_prompt})

        request_body: Dict[str, Any] = {
            "model": model_to_use,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            request_body["max_tokens"] = max_tokens
        elif schema is not None:
            request_body["max_tokens"] = 2048

        if schema is not None:
            request_body["response_format"] = {"type": "json_object"}

        start_time = time.perf_counter()
        retries = 0
        max_retries = self.settings.nebius_max_retries
        response: Optional[httpx.Response] = None
        upstream_req_id = None

        # Execute under concurrency semaphore
        async with self.controller.semaphore:
            while retries <= max_retries:
                try:
                    response = await client.post("/chat/completions", json=request_body)
                    upstream_req_id = response.headers.get("x-request-id") or response.headers.get("request-id")

                    # Handle 400 with response_format not supported
                    if response.status_code == 400 and "response_format" in response.text:
                        request_body.pop("response_format", None)
                        response = await client.post("/chat/completions", json=request_body)

                    # Non-retryable client errors (401, 403, 404, 422)
                    if response.status_code in (401, 403):
                        self.controller.record_failure()
                        err_msg = f"Nebius authentication failure (HTTP {response.status_code})"
                        logger.error(err_msg)
                        req = getattr(response, "request", None) or httpx.Request("POST", "/chat/completions")
                        sanitized_text, _ = redact_secrets(response.text)
                        sanitized_resp = httpx.Response(response.status_code, request=req, text=sanitized_text)
                        raise httpx.HTTPStatusError(
                            message=err_msg,
                            request=req,
                            response=sanitized_resp,
                        )

                    if response.status_code == 404:
                        self._cached_available_models = None
                        self._resolved_model = None
                        alt_model = await self.resolve_model(client, None)
                        if alt_model and alt_model != model_to_use:
                            logger.info(f"404 on model {model_to_use}; retrying with {alt_model}")
                            request_body["model"] = alt_model
                            model_to_use = alt_model
                            continue
                        else:
                            logger.error(f"Nebius API model not found: {model_to_use} ({response.text})")
                            response.raise_for_status()

                    if response.status_code == 429:
                        # Rate limited
                        self.controller.record_failure()
                        retry_after = float(response.headers.get("Retry-After", 2.0))
                        if retries < max_retries:
                            retries += 1
                            logger.warning(f"Nebius rate limited (429); backing off for {retry_after}s (retry {retries}/{max_retries})")
                            await asyncio.sleep(min(retry_after, 10.0))
                            continue
                        raise ModelRateLimitedError("Nebius rate limit exceeded after maximum retries")

                    # Retryable server errors (500, 502, 503, 504)
                    if response.status_code in (500, 502, 503, 504):
                        if retries < max_retries:
                            retries += 1
                            backoff = (2 ** retries) * 0.5
                            logger.warning(f"Nebius server error ({response.status_code}); retrying in {backoff}s")
                            await asyncio.sleep(backoff)
                            continue

                    response.raise_for_status()
                    break

                except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as net_err:
                    if retries < max_retries:
                        retries += 1
                        backoff = (2 ** retries) * 0.5
                        logger.warning(f"Nebius connection error: {type(net_err).__name__}; retrying in {backoff}s")
                        await asyncio.sleep(backoff)
                        continue
                    self.controller.record_failure()
                    raise

        if response is None:
            self.controller.record_failure()
            raise RuntimeError("Nebius request failed without response")

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        result = response.json()
        choice = (result.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or msg.get("reasoning") or msg.get("reasoning_content") or ""
        usage = result.get("usage", {}) or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or 0)

        structured_data = None
        if schema is not None:
            structured_data = extract_json_from_text(content)

        cost = self._estimate_cost({"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}, model_to_use)
        self.controller.record_success(cost)

        model_resp = ModelResponse(
            content=content,
            structured_data=structured_data,
            model_used=result.get("model", model_to_use),
            provider="nebius",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            cost=cost,
            inference=True,
            endpoint=self._get_base_url(),
        )

        # Store in cache
        if should_cache:
            self.controller.set_cached(cache_key, model_resp.model_dump())

        # Generate execution record
        response_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
        exec_record = ModelExecutionRecord(
            execution_id=str(uuid.uuid4()),
            incident_id=incident_id,
            job_id=job_id,
            provider="nebius",
            provider_state=ProviderState.NEBIUS_NVIDIA_ACTIVE,
            model_id=result.get("model", model_to_use),
            endpoint_mode="hosted",
            task_id=task_id,
            task_version=self.settings.structured_output_schema_version,
            prompt_template_version=self.settings.prompt_template_version,
            structured_output_schema_version=self.settings.structured_output_schema_version,
            redaction_count=redaction_count,
            request_id=upstream_req_id,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time)),
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            latency_ms=latency_ms,
            response_hash=response_hash,
            suggestions_received=1 if structured_data else 0,
            suggestions_accepted=1 if structured_data else 0,
            suggestions_rejected=0,
            validation_result=ValidationResult.ACCEPTED if structured_data else ValidationResult.PARTIAL,
            fallback_used=False,
            usage={"input_tokens": prompt_tokens, "output_tokens": completion_tokens},
        )
        get_execution_store().record(exec_record)

        return model_resp

    async def execute_task(
        self,
        task_type: ModelTaskType,
        input_data: BaseModel,
        incident_id: str,
        job_id: Optional[str] = None,
        referenced_artifact_ids: Optional[List[str]] = None,
        referenced_record_ids: Optional[List[str]] = None,
    ) -> Tuple[Optional[BaseModel], ModelExecutionRecord]:
        """
        Execute a declared bounded task against Nebius with schema validation.
        """
        spec = TASK_REGISTRY.get(task_type)
        if not spec:
            raise ValueError(f"Unknown model task type: {task_type}")

        start_time = time.perf_counter()
        started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time))
        input_json = json.dumps(input_data.model_dump(), sort_keys=True)
        raw_prompt = wrap_untrusted_input(
            f"Execute the task '{task_type.value}' version {spec.task_version}.", input_json
        )
        redacted_prompt, redactions = redact_secrets(raw_prompt)

        execution_id = str(uuid.uuid4())
        model_name = self.settings.nebius_model_id or "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"

        try:
            resp = await self.generate(
                prompt=redacted_prompt,
                schema=spec.output_schema,
                max_tokens=spec.max_output_tokens,
                incident_id=incident_id,
                job_id=job_id,
                task_id=task_type.value,
            )
            completed_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            resp_hash = f"sha256:{hashlib.sha256(resp.content.encode('utf-8')).hexdigest()}"

            parsed_output = None
            if resp.structured_data:
                try:
                    parsed_output = spec.output_schema(**resp.structured_data)
                except Exception as p_err:
                    logger.warning("Structured data parsing failed: %s", p_err)

            exec_record = ModelExecutionRecord(
                execution_id=execution_id,
                incident_id=incident_id,
                job_id=job_id,
                provider="nebius",
                provider_state=ProviderState.NEBIUS_NVIDIA_ACTIVE,
                model_id=resp.model_used or model_name,
                endpoint_mode="hosted",
                task_id=task_type.value,
                task_version=spec.task_version,
                prompt_template_version=self.settings.prompt_template_version,
                structured_output_schema_version=self.settings.structured_output_schema_version,
                input_artifact_ids=referenced_artifact_ids or [],
                input_record_ids=referenced_record_ids or [],
                redaction_count=redactions,
                started_at=started_iso,
                completed_at=completed_iso,
                latency_ms=latency_ms,
                response_hash=resp_hash,
                suggestions_received=1 if parsed_output else 0,
                suggestions_accepted=1 if parsed_output else 0,
                suggestions_rejected=0 if parsed_output else 1,
                validation_result=ValidationResult.ACCEPTED if parsed_output else ValidationResult.REJECTED,
                fallback_used=False,
                usage=resp.usage or {"input_tokens": None, "output_tokens": None},
            )
            get_execution_store().record(exec_record)
            return parsed_output, exec_record

        except Exception as exc:
            completed_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            error_code = type(exc).__name__
            exec_record = ModelExecutionRecord(
                execution_id=execution_id,
                incident_id=incident_id,
                job_id=job_id,
                provider="nebius",
                provider_state=ProviderState.NEBIUS_NVIDIA_DEGRADED,
                model_id=model_name,
                endpoint_mode="hosted",
                task_id=task_type.value,
                task_version=spec.task_version,
                prompt_template_version=self.settings.prompt_template_version,
                structured_output_schema_version=self.settings.structured_output_schema_version,
                input_artifact_ids=referenced_artifact_ids or [],
                input_record_ids=referenced_record_ids or [],
                redaction_count=redactions,
                started_at=started_iso,
                completed_at=completed_iso,
                latency_ms=latency_ms,
                response_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
                suggestions_received=0,
                suggestions_accepted=0,
                suggestions_rejected=0,
                validation_result=ValidationResult.ERROR,
                fallback_used=True,
                error_code=error_code,
                usage={"input_tokens": None, "output_tokens": None},
            )
            get_execution_store().record(exec_record)
            return None, exec_record

    def _estimate_cost(self, usage: Dict[str, Any], model: str) -> float:
        """Estimate cost based on token usage."""
        rate = 0.0007  # $0.0007 per 1K tokens for Llama-3.1-Nemotron-70B
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        return ((prompt_tokens + completion_tokens) / 1000.0) * rate

    async def aclose(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def probe(self) -> Dict[str, Any]:
        """
        Probe Nebius endpoint to report real reachability and active NVIDIA model.
        """
        started = time.perf_counter()
        base_url = self._get_base_url()
        configured_nvidia = self.settings.nebius_model_id or "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"

        if not self.is_available():
            return {
                "endpoint": base_url,
                "reachable": False,
                "latency_ms": None,
                "models": [],
                "provider_state": ProviderState.LOCAL_DETERMINISTIC_ONLY.value,
                "active_model": configured_nvidia,
                "error": "no API key configured",
            }

        try:
            client = await self._get_client()
            models = await self._get_available_models(client)
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            active_model = await self.resolve_model(client)
            return {
                "endpoint": base_url,
                "reachable": True,
                "latency_ms": elapsed,
                "models": models or [active_model],
                "active_model": active_model,
                "provider_state": ProviderState.NEBIUS_NVIDIA_ACTIVE.value,
            }
        except Exception as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            return {
                "endpoint": base_url,
                "reachable": False,
                "latency_ms": elapsed,
                "models": [],
                "active_model": configured_nvidia,
                "provider_state": ProviderState.NEBIUS_NVIDIA_DEGRADED.value,
                "error": f"{type(exc).__name__}: {exc}",
            }

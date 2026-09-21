"""
Nebius model gateway provider.
Calls real Nebius Token Factory APIs when credentials are available.
"""
from typing import Any, Dict, Optional, Type
import httpx
from pydantic import BaseModel
from .base import ModelGateway, ModelResponse, extract_json_from_text
from cauveris.config import get_settings
import logging

logger = logging.getLogger(__name__)


class CredentialNotConfigured(Exception):
    """Raised when Nebius credentials are not configured."""
    pass


class NebiusModelGateway(ModelGateway):
    """Nebius model gateway that calls real APIs."""

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    def is_available(self) -> bool:
        """Check if Nebius credentials are configured."""
        return bool(self.settings.nebius_api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.nebius_base_url,
                headers={
                    "Authorization": f"Bearer {self.settings.nebius_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

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
                "Optional: NEBIUS_BASE_URL (defaults to https://api.nebius.ai/v1)"
            )

        client = await self._get_client()

        # Prepare request body
        request_body: Dict[str, Any] = {
            "model": self.settings.model_reasoning,  # Use reasoning model for complex tasks
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }

        if max_tokens is not None:
            request_body["max_tokens"] = max_tokens

        # Add schema for structured output if requested
        if schema is not None:
            request_body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                },
            }

        try:
            response = await client.post("/chat/completions", json=request_body)
            response.raise_for_status()
            result = response.json()

            # Extract content
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})

            # Try to parse structured data if schema was provided
            structured_data = None
            if schema is not None:
                structured_data = extract_json_from_text(content)
                if structured_data is None:
                    # If we requested structured output but didn't get valid JSON,
                    # the API might have returned it directly in the response format
                    # depending on how Nebius implements structured output
                    pass

            return ModelResponse(
                content=content,
                structured_data=structured_data,
                model_used=result.get("model", self.settings.model_reasoning),
                provider="nebius",
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                cost=self._estimate_cost(usage, self.settings.model_reasoning),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Nebius API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error calling Nebius API: {e}")
            raise

    def _estimate_cost(self, usage: Dict[str, Any], model: str) -> float:
        """Estimate cost based on token usage."""
        # Rough estimates - adjust based on actual Nebius pricing
        # These are placeholder values
        rates_per_1k_tokens = {
            "nemotron-3-nano": 0.0001,
            "nemotron-3-super": 0.0003,
            "nemotron-3-ultra": 0.0010,
        }

        rate = rates_per_1k_tokens.get(model, 0.0003)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = prompt_tokens + completion_tokens

        return (total_tokens / 1000) * rate

    async def aclose(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

"""
Abstract base classes for model gateways.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from cauveris.schemas.base import BaseEntity
import json


class ModelResponse(BaseEntity):
    """Standardized response from model gateway."""
    content: str = Field(..., description="Raw model response content")
    structured_data: Optional[Dict[str, Any]] = Field(None, description="Parsed structured data if applicable")
    model_used: str = Field(..., description="Identifier of the model used")
    provider: str = Field(..., description="Provider name (local, nebius, etc.)")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token usage statistics")
    cost: Optional[float] = Field(None, description="Cost in USD")


class ModelGateway(ABC):
    """Abstract base class for model gateways."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        schema: Optional[type[BaseModel]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ModelResponse:
        """
        Generate a response from the model.

        Args:
            prompt: The input prompt
            schema: Optional Pydantic schema for structured output
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            ModelResponse with content and optionally structured data
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the model gateway is properly configured and available."""
        pass


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to extract JSON from model text output.

    Args:
        text: Raw model output

    Returns:
        Parsed JSON dict or None if not found/invalid
    """
    import re

    # Look for JSON block in markdown
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Look for raw JSON object
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return None

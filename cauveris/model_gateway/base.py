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
    structured_data: Optional[Dict[str, Any]] = Field(
        None, description="Parsed structured data if applicable"
    )
    model_used: str = Field(..., description="Identifier of the model used")
    provider: str = Field(..., description="Provider name (local-llm, nebius, etc.)")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token usage statistics")
    cost: Optional[float] = Field(None, description="Cost in USD")
    #: Whether a *generative model* produced this content.
    #:
    #: A gateway can always return something - a cache hit, a template, a
    #: hand-written default.  Such a response is a valid
    #: :class:`ModelResponse`, but presenting it as an inference would be a
    #: mock disguised as a result, so consumers check this flag before they
    #: treat the content as something a model concluded.
    inference: bool = Field(
        True,
        description="True when a generative model produced this content",
    )
    #: Where the content came from, when that is not implied by the provider.
    endpoint: Optional[str] = Field(
        None, description="The endpoint that served this response"
    )


class ModelGateway(ABC):
    """Abstract base class for model gateways."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        schema: Optional[type[BaseModel]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
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
    Attempt to extract JSON from model text output, stripping thinking traces if present.

    Args:
        text: Raw model output

    Returns:
        Parsed JSON dict or None if not found/invalid
    """
    import re

    if not text or not text.strip():
        return None

    # First attempt: if text is already pure JSON
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict):
            # If the model wrapped the actual payload in a top-level schema definition,
            # unwrapping or returning data
            return data
    except Exception:
        pass

    # Strip thinking / reasoning traces (e.g. Nemotron / DeepSeek COT)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"Here's a thinking process:.*?(?=(\n\s*\{|\n\s*```))", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip()

    # Look for JSON blocks in markdown (evaluate from last to first since final answer is at end)
    code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    for block in reversed(code_blocks):
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Look for raw JSON objects with matching braces
    for start_idx in range(len(cleaned)):
        if cleaned[start_idx] == "{":
            # Count brace depth to find matching closing brace
            depth = 0
            for end_idx in range(start_idx, len(cleaned)):
                if cleaned[end_idx] == "{":
                    depth += 1
                elif cleaned[end_idx] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = cleaned[start_idx : end_idx + 1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict):
                                # If this is a valid dict, keep checking if there's a later (final) one
                                return parsed
                        except json.JSONDecodeError:
                            pass
                        break

    # Fallback to greedy search
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return None

"""
Provider fallback for the model gateway.

A single provider is a single point of failure.  The remote provider is
missing its credential, the local server is down the same way the network is,
and the provider that *is* reachable may be the one that is rate-limited.
So the gateway is built as a chain: each provider is tried in turn, and the
first one that answers wins.

The chain never pretends.  A response carries the provider that actually
produced it, and every attempt - the ones that failed as well as the one
that succeeded - is recorded so an operator can see *why* a particular model
was used, and so a degraded answer is visible rather than silent.
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional, Type

from pydantic import BaseModel

from .base import ModelGateway, ModelResponse

logger = logging.getLogger(__name__)

__all__ = ["FallbackModelGateway", "AllProvidersFailed", "ProviderAttempt"]


class ProviderAttempt(BaseModel):
    """One provider's turn in the chain."""

    provider: str
    ok: bool
    error: Optional[str] = None
    elapsed_ms: float = 0.0


class AllProvidersFailed(Exception):
    """Every provider in the chain refused or failed to answer."""

    def __init__(self, attempts: List[ProviderAttempt]):
        self.attempts = attempts
        detail = "; ".join(
            f"{a.provider}: {a.error}" for a in attempts if a.error
        ) or "no providers configured"
        super().__init__(f"All model providers failed ({detail})")


class FallbackModelGateway(ModelGateway):
    """
    Tries a list of gateways in order until one of them answers.

    The order is the operator's policy: the cloud provider first because it
    is the strongest, the on-device model afterwards because it is the only
    one that survives the network being the thing that broke.
    """

    def __init__(self, gateways: List[ModelGateway], *, name: str = "fallback"):
        if not gateways:
            raise ValueError("a fallback gateway needs at least one provider")
        self.gateways = gateways
        self.name = name

    def is_available(self) -> bool:
        """Whether any provider in the chain is usable."""
        return any(gateway.is_available() for gateway in self.gateways)

    @property
    def provider_names(self) -> List[str]:
        """The providers in the chain, in the order they are tried."""
        names = []
        for gateway in self.gateways:
            names.append(type(gateway).__name__)
        return names

    async def generate(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """
        Ask each provider in turn; return the first usable answer.

        A provider that returns a response which is not an inference - a
        template, a placeholder - does not stop the chain: the next provider
        is still asked, because a real answer from a weaker model beats a
        fabricated answer from a stronger one.
        """
        attempts: List[ProviderAttempt] = []

        for gateway in self.gateways:
            provider = type(gateway).__name__
            started = time.perf_counter()
            try:
                response = await gateway.generate(
                    prompt=prompt,
                    schema=schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
            except Exception as exc:
                elapsed = round((time.perf_counter() - started) * 1000.0, 2)
                logger.warning(
                    "Model provider %s failed after %.2f ms: %s", provider, elapsed, exc
                )
                attempts.append(
                    ProviderAttempt(
                        provider=provider,
                        ok=False,
                        error=f"{type(exc).__name__}: {exc}",
                        elapsed_ms=elapsed,
                    )
                )
                continue

            elapsed = round((time.perf_counter() - started) * 1000.0, 2)
            if not getattr(response, "inference", True):
                logger.info(
                    "Model provider %s returned no inference; trying the next provider",
                    provider,
                )
                attempts.append(
                    ProviderAttempt(
                        provider=provider,
                        ok=False,
                        error="provider returned no inference",
                        elapsed_ms=elapsed,
                    )
                )
                continue

            attempts.append(
                ProviderAttempt(provider=provider, ok=True, elapsed_ms=elapsed)
            )
            response.usage = {
                **(response.usage or {}),
                "provider_attempts": [a.model_dump() for a in attempts],
                "fallback_chain": self.provider_names,
            }
            return response

        raise AllProvidersFailed(attempts)

    async def aclose(self) -> None:
        """Close every provider that holds a connection."""
        for gateway in self.gateways:
            closer = getattr(gateway, "aclose", None)
            if closer is None:
                continue
            try:
                await closer()
            except Exception as exc:  # closing must not raise
                logger.debug("Could not close %s: %s", type(gateway).__name__, exc)

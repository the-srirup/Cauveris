"""
Model gateway abstraction for Cauveris.

The gateway is a chain of providers, not a single client:

1. **Nebius Token Factory** - the hosted models, used when a key is set.
2. **A local model server** - Ollama, vLLM, LM Studio or anything else that
   speaks the OpenAI chat-completions protocol.

The chain exists because the platform has to keep working when the hosted
provider is down, and because on a robot the network being down is often the
incident being investigated.  Each provider is tried in order and the first
one that produces an actual inference wins.
"""

import logging
from typing import Optional

from .base import ModelGateway, ModelResponse
from .fallback import AllProvidersFailed, FallbackModelGateway, ProviderAttempt
from .local import LocalModelGateway, NoLocalModelAvailable
from .nebius import CredentialNotConfigured, NebiusModelGateway
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


def create_model_gateway(
    force_local: bool = False, timeout: Optional[float] = None
) -> ModelGateway:
    """
    Build the gateway chain for this deployment.

    Args:
        force_local: Skip the hosted provider and use only local servers.
            Used by tests that must not touch the network.
        timeout: Per-request timeout in seconds.  A health check passes a
            short one; a reasoning call uses the configured default.

    Returns:
        A :class:`FallbackModelGateway`.  The chain is always returned, even
        when it holds a single provider, so that callers can rely on the
        chain's shape rather than on the deployment's configuration.
    """
    settings = get_settings()
    providers: list[ModelGateway] = []

    if not force_local and settings.nebius_api_key:
        providers.append(NebiusModelGateway(timeout=timeout))
    elif not force_local:
        logger.info(
            "NEBIUS_API_KEY is not configured; the hosted model provider is "
            "not part of the gateway chain. Local servers, if any, will be "
            "used instead."
        )

    providers.append(
        LocalModelGateway(
            timeout=timeout,
            probe_timeout=min(timeout, 1.5) if timeout is not None else None,
        )
    )

    return FallbackModelGateway(providers)


__all__ = [
    "ModelGateway",
    "ModelResponse",
    "LocalModelGateway",
    "NebiusModelGateway",
    "FallbackModelGateway",
    "ProviderAttempt",
    "AllProvidersFailed",
    "NoLocalModelAvailable",
    "CredentialNotConfigured",
    "create_model_gateway",
]

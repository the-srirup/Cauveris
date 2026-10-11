"""
Model gateway abstraction for Cauveris.
Supports local fixture providers and real Nebius API providers.
"""

from .base import ModelGateway
from .local import LocalModelGateway
from .nebius import NebiusModelGateway
from cauveris.config import get_settings


def create_model_gateway(force_local: bool = False) -> ModelGateway:
    """
    Factory function to create the appropriate model gateway.

    Args:
        force_local: If True, always returns LocalModelGateway (for testing only)

    Returns:
        ModelGateway instance (Nebius for production, Local for testing)

    Production behavior:
        - Default: Returns NebiusModelGateway (requires NEBIUS_API_KEY)
        - If NEBIUS_API_KEY not set: Falls back to LocalModelGateway with warning
        - If force_local=True: Returns LocalModelGateway (testing only)
    """
    if force_local:
        return LocalModelGateway()

    settings = get_settings()
    if settings.nebius_api_key:
        return NebiusModelGateway()

    # Production fallback - warn but use local
    import logging

    logger = logging.getLogger(__name__)
    logger.warning(
        "NEBIUS_API_KEY not configured! Falling back to LocalModelGateway (test fixtures). "
        "Set NEBIUS_API_KEY environment variable for production use."
    )
    return LocalModelGateway()


__all__ = ["ModelGateway", "LocalModelGateway", "NebiusModelGateway", "create_model_gateway"]

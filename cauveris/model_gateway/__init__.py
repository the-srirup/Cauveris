"""
Model gateway abstraction and Nebius NVIDIA provider integration for Cauveris.
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import ModelGateway, ModelResponse, extract_json_from_text
from .circuit_breaker import (
    BudgetExceededError,
    CircuitBreakerOpen,
    ConcurrencyAndCostController,
    get_controller,
)
from .enums import (
    ModelAssistanceStatus,
    ModelTaskType,
    ProviderState,
    ValidationResult,
)
from .fallback import AllProvidersFailed, FallbackModelGateway, ProviderAttempt
from .local import LocalModelGateway, NoLocalModelAvailable
from .nebius import (
    CredentialNotConfigured,
    ModelRateLimitedError,
    NebiusModelGateway,
    normalize_nebius_url,
)
from .records import (
    ModelExecutionRecord,
    ModelExecutionStore,
    get_execution_store,
)
from .security import (
    MAX_PROMPT_INPUT_CHARS,
    redact_secrets,
    validate_contained_ids,
    wrap_untrusted_input,
)
from .tasks import (
    TASK_REGISTRY,
    EvidenceRecommendation,
    ExplanationGenerationInput,
    ExplanationGenerationOutput,
    HypothesisProposalInput,
    HypothesisProposalOutput,
    LogCluster,
    LogClusteringInput,
    LogClusteringOutput,
    MissingEvidenceInput,
    MissingEvidenceOutput,
    ProposedControlAdjustment,
    ProposedHypothesis,
    ProposedRepairStrategy,
    ProposedTermMapping,
    RepairStrategyInput,
    RepairStrategyOutput,
    TaskSpecification,
    TerminologyMappingInput,
    TerminologyMappingOutput,
)
from .validators import (
    VALIDATOR_VERSION,
    validate_explanation,
    validate_hypothesis_proposal,
    validate_log_clustering,
    validate_missing_evidence,
    validate_repair_strategy,
    validate_terminology_mapping,
)
from cauveris.config import get_settings

logger = logging.getLogger(__name__)


def create_model_gateway(
    force_local: bool = False, timeout: Optional[float] = None
) -> ModelGateway:
    """
    Build the gateway chain for this deployment.
    """
    settings = get_settings()
    providers: list[ModelGateway] = []

    if not force_local and settings.nebius_api_key and settings.nebius_enabled:
        providers.append(NebiusModelGateway(timeout=timeout))
    elif not force_local:
        logger.info(
            "NEBIUS_API_KEY is not configured or Nebius is disabled; the hosted provider is "
            "not active. Local deterministic fallback will be used."
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
    "extract_json_from_text",
    "LocalModelGateway",
    "NebiusModelGateway",
    "FallbackModelGateway",
    "ProviderAttempt",
    "AllProvidersFailed",
    "NoLocalModelAvailable",
    "CredentialNotConfigured",
    "ModelRateLimitedError",
    "create_model_gateway",
    "normalize_nebius_url",
    "ProviderState",
    "ModelTaskType",
    "ModelAssistanceStatus",
    "ValidationResult",
    "ModelExecutionRecord",
    "ModelExecutionStore",
    "get_execution_store",
    "redact_secrets",
    "wrap_untrusted_input",
    "validate_contained_ids",
    "MAX_PROMPT_INPUT_CHARS",
    "TASK_REGISTRY",
    "TaskSpecification",
    "TerminologyMappingInput",
    "TerminologyMappingOutput",
    "ProposedTermMapping",
    "LogClusteringInput",
    "LogClusteringOutput",
    "LogCluster",
    "HypothesisProposalInput",
    "HypothesisProposalOutput",
    "ProposedHypothesis",
    "RepairStrategyInput",
    "RepairStrategyOutput",
    "ProposedRepairStrategy",
    "ProposedControlAdjustment",
    "MissingEvidenceInput",
    "MissingEvidenceOutput",
    "EvidenceRecommendation",
    "ExplanationGenerationInput",
    "ExplanationGenerationOutput",
    "VALIDATOR_VERSION",
    "validate_terminology_mapping",
    "validate_log_clustering",
    "validate_missing_evidence",
    "validate_hypothesis_proposal",
    "validate_repair_strategy",
    "validate_explanation",
    "ConcurrencyAndCostController",
    "get_controller",
    "CircuitBreakerOpen",
    "BudgetExceededError",
]

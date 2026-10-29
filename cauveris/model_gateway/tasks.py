"""
Bounded Model Task Definitions and Schemas for Cauveris.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .enums import ModelTaskType


# ---------------------------------------------------------------------------
# 1. TERMINOLOGY_MAPPING
# ---------------------------------------------------------------------------

class TerminologyMappingInput(BaseModel):
    unfamiliar_terms: List[str] = Field(..., description="Unknown or non-standard metric/signal names")
    source_references: List[str] = Field(default_factory=list, description="Associated file or component paths")
    canonical_vocabulary: List[str] = Field(
        default_factory=list, description="Recognized canonical signals in Cauveris"
    )


class ProposedTermMapping(BaseModel):
    unfamiliar_term: str = Field(..., description="The unfamiliar term analyzed")
    proposed_canonical_signal: str = Field(..., description="Proposed canonical target signal")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Proposal confidence score")
    explanation: str = Field(..., description="Rationale for the mapping")
    alternatives: List[str] = Field(default_factory=list, description="Alternative possible mappings")


class TerminologyMappingOutput(BaseModel):
    mappings: List[ProposedTermMapping] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. LOG_CLUSTERING
# ---------------------------------------------------------------------------

class LogClusteringInput(BaseModel):
    bounded_log_samples: List[str] = Field(..., description="Redacted log snippets")
    event_ids: List[str] = Field(..., description="Known event IDs corresponding to samples")
    timestamps: List[str] = Field(default_factory=list, description="Timestamps")


class LogCluster(BaseModel):
    cluster_id: str
    description: str
    representative_event_ids: List[str] = Field(default_factory=list)
    event_count: int = 0


class LogClusteringOutput(BaseModel):
    clusters: List[LogCluster] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 3. HYPOTHESIS_PROPOSAL
# ---------------------------------------------------------------------------

class HypothesisProposalInput(BaseModel):
    evidence_summary: Dict[str, Any] = Field(..., description="Normalized summary of incident telemetry")
    unknown_signals: List[str] = Field(default_factory=list, description="Unmapped signals")
    contradictions: List[str] = Field(default_factory=list, description="Observed invariant contradictions")
    supported_mechanisms: List[str] = Field(
        default_factory=list, description="Mechanisms registered in Cauveris"
    )


class ProposedHypothesis(BaseModel):
    mechanism_id: str = Field(..., description="Proposed mechanism from supported registry")
    causal_claim: str = Field(..., description="Technical explanation of the failure mode")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="Evidence artifact references")
    contradictory_evidence_ids: List[str] = Field(default_factory=list, description="Contradicting evidence references")
    missing_evidence: List[str] = Field(default_factory=list, description="Telemetry needed to prove or falsify")
    confidence: float = Field(0.8, ge=0.0, le=1.0, description="Proposed confidence")


class HypothesisProposalOutput(BaseModel):
    proposals: List[ProposedHypothesis] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. REPAIR_STRATEGY_PROPOSAL
# ---------------------------------------------------------------------------

class RepairStrategyInput(BaseModel):
    validated_hypothesis: Dict[str, Any] = Field(..., description="Active accepted hypothesis")
    editable_controls: List[Dict[str, Any]] = Field(..., description="Config parameters discovered in bundle")
    repair_strategy_registry: List[str] = Field(
        default_factory=list, description="Registered repair strategies"
    )
    safety_constraints: Dict[str, Any] = Field(default_factory=dict, description="Numerical invariant limits")


class ProposedControlAdjustment(BaseModel):
    config_file: str
    parameter_key: str
    current_value: Any
    proposed_value: Any
    units: Optional[str] = None


class ProposedRepairStrategy(BaseModel):
    strategy_id: str
    proposed_controls: List[ProposedControlAdjustment] = Field(default_factory=list)
    rationale: str
    risks: List[str] = Field(default_factory=list)


class RepairStrategyOutput(BaseModel):
    strategies: List[ProposedRepairStrategy] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 5. MISSING_EVIDENCE_RECOMMENDATION
# ---------------------------------------------------------------------------

class MissingEvidenceInput(BaseModel):
    capability_report: Dict[str, Any]
    missing_evidence: List[str]
    unsupported_artifacts: List[str]


class EvidenceRecommendation(BaseModel):
    evidence_type: str
    priority: str = "HIGH"
    rationale: str


class MissingEvidenceOutput(BaseModel):
    recommendations: List[EvidenceRecommendation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 6. EXPLANATION_GENERATION
# ---------------------------------------------------------------------------

class ExplanationGenerationInput(BaseModel):
    deterministic_results: Dict[str, Any]
    approved_terminology: Dict[str, str] = Field(default_factory=dict)


class ExplanationGenerationOutput(BaseModel):
    user_explanation: str
    technical_summary: str
    acknowledged_limitations: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Task Specification Registry
# ---------------------------------------------------------------------------

class TaskSpecification(BaseModel):
    task_id: ModelTaskType
    task_version: str = "1.0"
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    max_input_chars: int = 30_000
    max_output_tokens: int = 2048
    timeout_seconds: float = 30.0
    max_retries: int = 2
    is_required: bool = False


TASK_REGISTRY: Dict[ModelTaskType, TaskSpecification] = {
    ModelTaskType.TERMINOLOGY_MAPPING: TaskSpecification(
        task_id=ModelTaskType.TERMINOLOGY_MAPPING,
        input_schema=TerminologyMappingInput,
        output_schema=TerminologyMappingOutput,
        max_input_chars=20_000,
        max_output_tokens=1024,
        timeout_seconds=20.0,
        is_required=False,
    ),
    ModelTaskType.LOG_CLUSTERING: TaskSpecification(
        task_id=ModelTaskType.LOG_CLUSTERING,
        input_schema=LogClusteringInput,
        output_schema=LogClusteringOutput,
        max_input_chars=35_000,
        max_output_tokens=1536,
        timeout_seconds=25.0,
        is_required=False,
    ),
    ModelTaskType.HYPOTHESIS_PROPOSAL: TaskSpecification(
        task_id=ModelTaskType.HYPOTHESIS_PROPOSAL,
        input_schema=HypothesisProposalInput,
        output_schema=HypothesisProposalOutput,
        max_input_chars=30_000,
        max_output_tokens=2048,
        timeout_seconds=30.0,
        is_required=False,
    ),
    ModelTaskType.REPAIR_STRATEGY_PROPOSAL: TaskSpecification(
        task_id=ModelTaskType.REPAIR_STRATEGY_PROPOSAL,
        input_schema=RepairStrategyInput,
        output_schema=RepairStrategyOutput,
        max_input_chars=25_000,
        max_output_tokens=2048,
        timeout_seconds=30.0,
        is_required=False,
    ),
    ModelTaskType.MISSING_EVIDENCE_RECOMMENDATION: TaskSpecification(
        task_id=ModelTaskType.MISSING_EVIDENCE_RECOMMENDATION,
        input_schema=MissingEvidenceInput,
        output_schema=MissingEvidenceOutput,
        max_input_chars=20_000,
        max_output_tokens=1024,
        timeout_seconds=15.0,
        is_required=False,
    ),
    ModelTaskType.EXPLANATION_GENERATION: TaskSpecification(
        task_id=ModelTaskType.EXPLANATION_GENERATION,
        input_schema=ExplanationGenerationInput,
        output_schema=ExplanationGenerationOutput,
        max_input_chars=25_000,
        max_output_tokens=2048,
        timeout_seconds=25.0,
        is_required=False,
    ),
}

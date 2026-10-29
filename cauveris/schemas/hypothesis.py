"""
Hypothesis-related schemas.
"""

from .base import BaseEntity, StatusLabel
from pydantic import Field
from typing import Any, Dict, List, Optional


class ProposedChange(BaseEntity):
    """
    One concrete configuration change a hypothesis proposes.

    The intervention text says *what* to try; this says *which knob* to turn
    and *to what value*.  Downstream stages - the sandbox, the digital twin,
    the patch forge and the verifier - read these fields instead of parsing
    English, so the same change is applied everywhere it matters.
    """

    #: The physical parameter to change, named as in the twin's parameter set
    #: (``batching_window_ms``, ``consumer_rate_hz``, ``qos_queue_depth``, ...).
    parameter: str = Field(..., description="Parameter to change")
    current_value: Optional[float] = Field(None, description="Value in force now")
    target_value: Optional[float] = Field(None, description="Value to set")
    #: The bundle file the change belongs in, relative to the bundle root.
    file: Optional[str] = Field(None, description="Configuration file to change")
    #: The key inside that file.
    config_key: Optional[str] = Field(None, description="Configuration key to change")
    rationale: Optional[str] = Field(None, description="Why this change is expected to help")
    #: Whether the change alone is expected to bring the system inside its
    #: budget.  False means it is necessary but not sufficient.
    sufficient_on_its_own: bool = Field(
        True, description="Whether this change alone restores compliance"
    )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "parameter": self.parameter,
            "current_value": self.current_value,
            "target_value": self.target_value,
            "file": self.file,
            "config_key": self.config_key,
            "rationale": self.rationale,
            "sufficient_on_its_own": self.sufficient_on_its_own,
        }


class Hypothesis(BaseEntity):
    """A falsifiable root-cause hypothesis."""

    hypothesis_id: str = Field(..., description="Unique identifier for the hypothesis")
    incident_id: Optional[str] = Field(None, description="Incident this hypothesis belongs to")
    causal_claim: str = Field(..., description="Concise causal claim")
    status: StatusLabel = Field(default=StatusLabel.INFERRED, description="Current status")
    supporting_artifact_ids: List[str] = Field(
        default_factory=list, description="IDs of supporting evidence"
    )
    supporting_evidence_ids: List[str] = Field(
        default_factory=list, description="IDs of supporting evidence records"
    )
    contradicting_artifact_ids: List[str] = Field(
        default_factory=list, description="IDs of contradicting evidence"
    )
    contradicting_evidence_ids: List[str] = Field(
        default_factory=list, description="IDs of contradicting evidence records"
    )
    evidence_links: List[Dict[str, Any]] = Field(
        default_factory=list, description="Explicit links to evidence artifacts, lines, and spans"
    )
    missing_evidence: List[str] = Field(
        default_factory=list, description="Description of missing evidence"
    )
    confidence_prior: float = Field(
        0.5, ge=0.0, le=1.0, description="Prior confidence in hypothesis"
    )
    confidence_rationale: Optional[str] = Field(
        None, description="Mathematical / evidentiary derivation rationale for confidence score"
    )
    provider_execution_id: Optional[str] = Field(
        None, description="Execution ID of model gateway call that proposed or assisted this hypothesis"
    )
    expected_observation: str = Field(
        ..., description="What should be observed if hypothesis is true"
    )
    falsifying_observation: str = Field(..., description="What would falsify the hypothesis")
    falsification_criteria: str = Field(
        "", description="Explicit falsification criteria and conditions"
    )
    speculative: bool = Field(
        False, description="Whether hypothesis lacks direct evidence grounding and is speculative"
    )
    intervention: str = Field(..., description="Proposed experiment to test hypothesis")
    estimated_trials: int = Field(1, description="Estimated number of trials needed")
    estimated_cost: float = Field(0.0, description="Estimated cost in compute units")
    likely_files: List[str] = Field(
        default_factory=list, description="Likely source files to examine"
    )
    likely_parameters: List[str] = Field(
        default_factory=list, description="Likely configuration parameters"
    )
    safety_constraints: List[str] = Field(
        default_factory=list, description="Safety constraints to consider"
    )
    proposed_changes: List[ProposedChange] = Field(
        default_factory=list,
        description="Machine-readable configuration changes this hypothesis proposes",
    )
    bundle_path: Optional[str] = Field(
        None, description="Path to the incident bundle this hypothesis came from"
    )

    @property
    def confidence(self) -> float:
        return self.confidence_prior

    @classmethod
    def _reconcile_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Reconcile supporting evidence
            supp_arts = data.get("supporting_artifact_ids") or []
            supp_evs = data.get("supporting_evidence_ids") or []
            if not supp_evs and supp_arts:
                data["supporting_evidence_ids"] = list(supp_arts)
            elif not supp_arts and supp_evs:
                data["supporting_artifact_ids"] = list(supp_evs)

            # Reconcile contradicting evidence
            contra_arts = data.get("contradicting_artifact_ids") or []
            contra_evs = data.get("contradicting_evidence_ids") or []
            if not contra_evs and contra_arts:
                data["contradicting_evidence_ids"] = list(contra_arts)
            elif not contra_arts and contra_evs:
                data["contradicting_artifact_ids"] = list(contra_evs)

            # Reconcile falsification criteria
            crit = data.get("falsification_criteria")
            obs = data.get("falsifying_observation")
            if not crit and obs:
                data["falsification_criteria"] = obs
            elif not obs and crit:
                data["falsifying_observation"] = crit

            # Confidence alias
            if "confidence" in data and "confidence_prior" not in data:
                data["confidence_prior"] = float(data["confidence"])

            # Grounding check: mark speculative if no supporting evidence
            has_evidence = bool(data.get("supporting_artifact_ids") or data.get("supporting_evidence_ids"))
            if not has_evidence and "speculative" not in data:
                data["speculative"] = True

        return data

    def __init__(self, **data: Any) -> None:
        reconciled = self._reconcile_fields(data)
        super().__init__(**reconciled)

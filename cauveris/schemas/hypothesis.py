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
    causal_claim: str = Field(..., description="Concise causal claim")
    status: StatusLabel = Field(default=StatusLabel.INFERRED, description="Current status")
    supporting_artifact_ids: List[str] = Field(
        default_factory=list, description="IDs of supporting evidence"
    )
    contradicting_artifact_ids: List[str] = Field(
        default_factory=list, description="IDs of contradicting evidence"
    )
    missing_evidence: List[str] = Field(
        default_factory=list, description="Description of missing evidence"
    )
    confidence_prior: float = Field(
        0.5, ge=0.0, le=1.0, description="Prior confidence in hypothesis"
    )
    expected_observation: str = Field(
        ..., description="What should be observed if hypothesis is true"
    )
    falsifying_observation: str = Field(..., description="What would falsify the hypothesis")
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
    #: The bundle the hypothesis was derived from.  It travels with the
    #: hypothesis so that every later stage - the sandbox, the simulation, the
    #: patch forge, the verifier - works on *this* incident's files instead of
    #: on whichever bundle it happens to find first.
    bundle_path: Optional[str] = Field(
        None, description="Path to the incident bundle this hypothesis came from"
    )

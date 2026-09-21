"""
Hypothesis-related schemas.
"""
from .base import BaseEntity, StatusLabel
from pydantic import Field
from typing import List


class Hypothesis(BaseEntity):
    """A falsifiable root-cause hypothesis."""
    hypothesis_id: str = Field(..., description="Unique identifier for the hypothesis")
    causal_claim: str = Field(..., description="Concise causal claim")
    status: StatusLabel = Field(default=StatusLabel.INFERRED, description="Current status")
    supporting_artifact_ids: List[str] = Field(default_factory=list, description="IDs of supporting evidence")
    contradicting_artifact_ids: List[str] = Field(default_factory=list, description="IDs of contradicting evidence")
    missing_evidence: List[str] = Field(default_factory=list, description="Description of missing evidence")
    confidence_prior: float = Field(0.5, ge=0.0, le=1.0, description="Prior confidence in hypothesis")
    expected_observation: str = Field(..., description="What should be observed if hypothesis is true")
    falsifying_observation: str = Field(..., description="What would falsify the hypothesis")
    intervention: str = Field(..., description="Proposed experiment to test hypothesis")
    estimated_trials: int = Field(1, description="Estimated number of trials needed")
    estimated_cost: float = Field(0.0, description="Estimated cost in compute units")
    likely_files: List[str] = Field(default_factory=list, description="Likely source files to examine")
    likely_parameters: List[str] = Field(default_factory=list, description="Likely configuration parameters")
    safety_constraints: List[str] = Field(default_factory=list, description="Safety constraints to consider")

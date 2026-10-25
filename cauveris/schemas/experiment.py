"""
Experiment-related schemas.
"""

from .base import BaseEntity, StatusLabel
from pydantic import Field
from typing import Optional, Dict, Any, List


class Experiment(BaseEntity):
    """A controlled experiment branch testing a hypothesis."""

    experiment_id: str = Field(..., description="Unique identifier for the experiment")
    hypothesis_id: str = Field(..., description="ID of hypothesis being tested")
    incident_id: Optional[str] = Field(
        None, description="Incident the hypothesis and the branch belong to"
    )
    branch_name: str = Field(..., description="Name of the sandbox branch")
    intervention: str = Field(..., description="Applied intervention")
    proposed_changes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Machine-readable configuration changes this experiment applies",
    )
    status: StatusLabel = Field(
        default=StatusLabel.INFERRED, description="Current experiment status"
    )
    trial_count: int = Field(0, description="Number of trials run")
    reproduction_count: int = Field(0, description="Number of times failure was reproduced")
    reproduction_rate: float = Field(0.0, ge=0.0, le=1.0, description="Rate of reproduction")
    failure_oracle: Optional[Dict[str, Any]] = Field(None, description="How failure is detected")
    logs_artifact_id: Optional[str] = Field(None, description="ID of logs artifact")
    metrics_artifact_id: Optional[str] = Field(None, description="ID of metrics artifact")
    replay_artifact_id: Optional[str] = Field(None, description="ID of replay artifact")
    conclusion: Optional[str] = Field(None, description="Experiment conclusion")
    trajectory: Optional[List[Dict[str, Any]]] = Field(
        None, description="Representative 2D spatial trajectory points"
    )
    trajectories: Optional[List[Dict[str, Any]]] = Field(
        None, description="Multi-trial trajectory runs"
    )

"""
Canonical Invariant Models.

Every experiment, model evaluation, and verification step must reference one
immutable, versioned invariant set.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class InvariantKind(str, Enum):
    OBSERVED = "OBSERVED"
    DECLARED = "DECLARED"
    DERIVED = "DERIVED"
    CALIBRATED = "CALIBRATED"
    INFERRED = "INFERRED"
    ASSUMED = "ASSUMED"


class InvariantAuthority(str, Enum):
    RUNTIME_CONFIG = "runtime_config"
    DEPLOYMENT_CONFIG = "deployment_config"
    MANIFEST = "manifest"
    TELEMETRY = "telemetry"
    OPERATOR_OVERRIDE = "operator_override"
    DERIVED_CONSTRAINT = "derived_constraint"
    MODEL_ASSUMPTION = "model_assumption"


class InvariantStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CONFLICTED = "CONFLICTED"
    UNAVAILABLE = "UNAVAILABLE"


class InvariantSetStatus(str, Enum):
    VALID = "VALID"
    CONFLICTED = "CONFLICTED"
    INCOMPLETE = "INCOMPLETE"


AUTHORITY_PRIORITY: Dict[InvariantAuthority, int] = {
    InvariantAuthority.RUNTIME_CONFIG: 100,
    InvariantAuthority.DEPLOYMENT_CONFIG: 90,
    InvariantAuthority.MANIFEST: 80,
    InvariantAuthority.TELEMETRY: 70,
    InvariantAuthority.OPERATOR_OVERRIDE: 60,
    InvariantAuthority.DERIVED_CONSTRAINT: 50,
    InvariantAuthority.MODEL_ASSUMPTION: 40,
}


class InvariantCandidate(BaseModel):
    """A single candidate source value for an invariant."""
    value: float
    unit: str
    source_artifact_id: Optional[str] = None
    source_locator: Optional[str] = None
    authority: InvariantAuthority = InvariantAuthority.RUNTIME_CONFIG
    confidence: float = 1.0


class InvariantConflict(BaseModel):
    """Record of conflicting values discovered for an invariant."""
    invariant_id: str
    status: str = "CONFLICTED"
    candidates: List[InvariantCandidate] = Field(default_factory=list)
    selected: Optional[float] = None
    selected_unit: Optional[str] = None
    verification_blocked: bool = True
    resolution_audit_id: Optional[str] = None
    resolution_reason: Optional[str] = None


class Invariant(BaseModel):
    """A canonical safety or operational invariant."""
    invariant_id: str
    version: str = "1"
    name: str
    value: Optional[float] = None
    unit: str
    kind: InvariantKind = InvariantKind.DECLARED
    source_artifact_id: Optional[str] = None
    source_locator: Optional[str] = None
    scope: str = "control_loop"
    authority: InvariantAuthority = InvariantAuthority.RUNTIME_CONFIG
    priority: int = 100
    confidence: float = 1.0
    uncertainty: Optional[float] = None
    status: InvariantStatus = InvariantStatus.ACTIVE
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class InvariantSet(BaseModel):
    """An immutable versioned set of invariants for an incident."""
    invariant_set_id: str
    incident_id: str
    version: str = "1.0.0"
    created_at: str
    invariants: Dict[str, Invariant] = Field(default_factory=dict)
    conflicts: List[InvariantConflict] = Field(default_factory=list)
    status: InvariantSetStatus = InvariantSetStatus.VALID

    def get_invariant(self, invariant_id: str) -> Optional[Invariant]:
        return self.invariants.get(invariant_id)

    def is_verification_blocked(self) -> bool:
        if self.status == InvariantSetStatus.CONFLICTED:
            return True
        return any(c.verification_blocked for c in self.conflicts)

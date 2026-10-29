"""
Canonical Calculation Provenance Framework.

Defines the 8 authoritative provenance classes across Cauveris:
  OBSERVED, DECLARED, DERIVED, CALIBRATED, INFERRED, SIMULATED, EXPLICIT_DEFAULT, UNAVAILABLE.

Ensures every numerical parameter, latency component, and simulation metric:
1. Bears an explicit ProvenanceClass.
2. Identifies its source artifact or file locator when available.
3. Provides a calculation rationale explaining how it was determined.
4. Refuses silent zeros or placeholder text for missing values, labeling them UNAVAILABLE.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class ProvenanceClass(str, Enum):
    """
    Authoritative provenance classes for all parameters and metrics.
    """
    #: Directly extracted from telemetry, metrics, traces, or runtime logs.
    OBSERVED = "OBSERVED"
    #: Declared explicitly in configuration files, manifests, or deployment specs.
    DECLARED = "DECLARED"
    #: Computed directly through exact mathematical formulas from OBSERVED or DECLARED inputs.
    DERIVED = "DERIVED"
    #: Fitted through statistical or regression modeling against observed system traces.
    CALIBRATED = "CALIBRATED"
    #: Logically deduced from physical or system constraints (e.g. OOM kill implies demand > limit).
    INFERRED = "INFERRED"
    #: Produced by execution of digital twin models or sandbox replay trials.
    SIMULATED = "SIMULATED"
    #: Known industrial baseline or policy default explicitly documented and flagged.
    EXPLICIT_DEFAULT = "EXPLICIT_DEFAULT"
    #: Parameter cannot be determined or resolved from available bundle artifacts.
    UNAVAILABLE = "UNAVAILABLE"


class ProvenanceRecord(BaseModel):
    """Detailed provenance tracking record for an individual parameter or metric."""

    parameter_id: str
    name: str = ""
    value: Optional[float] = None
    unit: str = "dimensionless"
    provenance: ProvenanceClass = ProvenanceClass.UNAVAILABLE
    source_artifact: Optional[str] = None
    source_locator: Optional[str] = None
    calculation_rationale: Optional[str] = None
    confidence: float = 1.0
    uncertainty: Optional[float] = None
    assumptions: List[str] = Field(default_factory=list)

    @property
    def display_value(self) -> str:
        """Formatted representation ensuring missing values display UNAVAILABLE."""
        if self.value is None or self.provenance == ProvenanceClass.UNAVAILABLE:
            return "UNAVAILABLE"
        if isinstance(self.value, float) and self.value.is_integer():
            return f"{int(self.value)} {self.unit}".strip()
        return f"{self.value:.2f} {self.unit}".strip()

    def to_provenance_dict(self) -> Dict[str, Any]:
        """Convert to API and frontend consumable dictionary."""
        return {
            "parameter_id": self.parameter_id,
            "name": self.name or self.parameter_id.replace("_", " ").title(),
            "value": self.value,
            "display_value": self.display_value,
            "unit": self.unit,
            "provenance": self.provenance.value,
            "provenance_class": self.provenance.value,
            "source_artifact": self.source_artifact,
            "source_locator": self.source_locator,
            "calculation_rationale": self.calculation_rationale,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "assumptions": self.assumptions,
            "is_evidence_backed": self.provenance in (
                ProvenanceClass.OBSERVED,
                ProvenanceClass.DECLARED,
                ProvenanceClass.DERIVED,
                ProvenanceClass.CALIBRATED,
            ),
        }


def normalize_provenance_string(source_str: Optional[str]) -> Tuple[ProvenanceClass, Optional[str]]:
    """
    Parse a source string with prefix (e.g. 'declared:config/worker.yaml') into
    its canonical ProvenanceClass and detailed source reference.
    """
    if not source_str:
        return ProvenanceClass.UNAVAILABLE, None

    clean = str(source_str).strip()
    lower = clean.lower()

    if lower.startswith("declared:"):
        return ProvenanceClass.DECLARED, clean[len("declared:"):].strip()
    if lower.startswith("observed:") or lower.startswith("measured:") or lower.startswith("metric:") or lower.startswith("log:"):
        return ProvenanceClass.OBSERVED, clean.split(":", 1)[1].strip() if ":" in clean else clean
    if lower.startswith("derived:"):
        return ProvenanceClass.DERIVED, clean[len("derived:"):].strip()
    if lower.startswith("calibrated:") or lower.startswith("fit:"):
        return ProvenanceClass.CALIBRATED, clean.split(":", 1)[1].strip() if ":" in clean else clean
    if lower.startswith("inferred:"):
        return ProvenanceClass.INFERRED, clean[len("inferred:"):].strip()
    if lower.startswith("simulated:") or lower.startswith("twin:"):
        return ProvenanceClass.SIMULATED, clean.split(":", 1)[1].strip() if ":" in clean else clean
    if lower.startswith("default:") or lower.startswith("explicit_default:"):
        return ProvenanceClass.EXPLICIT_DEFAULT, clean.split(":", 1)[1].strip() if ":" in clean else clean
    if lower.startswith("unavailable:") or lower == "unavailable":
        return ProvenanceClass.UNAVAILABLE, clean.split(":", 1)[1].strip() if ":" in clean else None

    # Check direct name matches
    for cls in ProvenanceClass:
        if lower == cls.value.lower():
            return cls, None

    return ProvenanceClass.OBSERVED, clean


def create_provenance_record(
    parameter_id: str,
    value: Optional[float],
    unit: str,
    provenance: ProvenanceClass,
    *,
    name: Optional[str] = None,
    source_artifact: Optional[str] = None,
    source_locator: Optional[str] = None,
    calculation_rationale: Optional[str] = None,
    confidence: float = 1.0,
    uncertainty: Optional[float] = None,
    assumptions: Optional[List[str]] = None,
) -> ProvenanceRecord:
    """Convenience constructor with validation."""
    if provenance == ProvenanceClass.UNAVAILABLE:
        value = None
        confidence = 0.0

    return ProvenanceRecord(
        parameter_id=parameter_id,
        name=name or parameter_id.replace("_", " ").title(),
        value=value,
        unit=unit,
        provenance=provenance,
        source_artifact=source_artifact,
        source_locator=source_locator,
        calculation_rationale=calculation_rationale,
        confidence=confidence,
        uncertainty=uncertainty,
        assumptions=assumptions or [],
    )

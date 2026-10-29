"""
Traceable Model Inputs & Sensitivity Analysis.

Ensures every numerical parameter ingested by digital twins, analysis layers,
or simulations has strict provenance, sensitivity classification, uncertainty,
and reproducible hashing.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from cauveris.invariants.units import normalize_value
from cauveris.analysis.provenance import ProvenanceClass

ModelInputKind = ProvenanceClass


class SensitivityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


MODEL_POLICY_VERSION = "2026.1"

# Versioned canonical parameter policy with scopes, rationale, sensitivity, and verification effects
DEFAULT_PARAMETER_POLICIES: Dict[str, Dict[str, Any]] = {
    "arrival_rate_hz": {
        "name": "Perception arrival rate",
        "default_value": 10.0,
        "unit": "Hz",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "sensor_producer",
        "default_reason": "Standard nominal frame rate for industrial RGB-D sensor streams",
        "verification_effect": "Directly controls queue backlog, buffer overflow, and end-to-end perception latency",
        "credible_range": (2.0, 30.0),
    },
    "batching_window_ms": {
        "name": "Dynamic batching window",
        "default_value": 100.0,
        "unit": "ms",
        "sensitivity": SensitivityLevel.HIGH,
        "valid_scope": "inference_server",
        "default_reason": "Nominal inference batching timeout in Triton / TorchServe serving configurations",
        "verification_effect": "Sets lower bound on server wait time before dispatching neural inference",
        "credible_range": (10.0, 400.0),
    },
    "max_batch_size": {
        "name": "Maximum batch size",
        "default_value": 8.0,
        "unit": "items",
        "sensitivity": SensitivityLevel.MEDIUM,
        "valid_scope": "inference_server",
        "default_reason": "Standard GPU memory batch packing limit for tensor cores",
        "verification_effect": "Influences compute duration and throughput scaling",
        "credible_range": (1.0, 32.0),
    },
    "server_workers": {
        "name": "Inference server worker pool size",
        "default_value": 1.0,
        "unit": "workers",
        "sensitivity": SensitivityLevel.HIGH,
        "valid_scope": "inference_server",
        "default_reason": "Single worker execution thread in base container deployment",
        "verification_effect": "Limits concurrent inference request processing capacity",
        "credible_range": (1.0, 8.0),
    },
    "transport_mean_ms": {
        "name": "Network transport mean delay",
        "default_value": 10.0,
        "unit": "ms",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "network",
        "default_reason": "Local wireless / edge industrial network baseline transport delay",
        "verification_effect": "Direct additive latency component on perception delivery",
        "credible_range": (2.0, 80.0),
    },
    "transport_sigma_ms": {
        "name": "Network transport jitter standard deviation",
        "default_value": 2.0,
        "unit": "ms",
        "sensitivity": SensitivityLevel.MEDIUM,
        "valid_scope": "network",
        "default_reason": "Standard edge transport jitter distribution",
        "verification_effect": "Adds tail latency variance across control cycles",
        "credible_range": (0.5, 20.0),
    },
    "qos_queue_depth": {
        "name": "ROS QoS subscriber queue depth",
        "default_value": 10.0,
        "unit": "items",
        "sensitivity": SensitivityLevel.HIGH,
        "valid_scope": "ros_subscriber",
        "default_reason": "Default ROS 2 QoS sensor history buffer depth",
        "verification_effect": "Controls backpressure drops when consumer is saturated",
        "credible_range": (1.0, 100.0),
    },
    "consumer_rate_hz": {
        "name": "Control loop sampling rate",
        "default_value": 10.0,
        "unit": "Hz",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "control_loop",
        "default_reason": "Robot motion control loop cycle rate",
        "verification_effect": "Determines how frequently perception frames are consumed by vehicle trajectory planner",
        "credible_range": (5.0, 50.0),
    },
    "resource_limit_mb": {
        "name": "Resource memory limit",
        "default_value": 1024.0,
        "unit": "MB",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "process",
        "default_reason": "Container memory cgroup limit",
        "verification_effect": "Hard threshold for OOM kill",
        "credible_range": (256.0, 8192.0),
    },
    "resource_demand_mb": {
        "name": "Resource memory demand",
        "default_value": 512.0,
        "unit": "MB",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "process",
        "default_reason": "Estimated working set footprint",
        "verification_effect": "Determines memory pressure ratio",
        "credible_range": (128.0, 4096.0),
    },
    "request_timeout_ms": {
        "name": "Client request timeout",
        "default_value": 500.0,
        "unit": "ms",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "client",
        "default_reason": "HTTP/gRPC client request deadline",
        "verification_effect": "Hard cutoff for dependency cancellation",
        "credible_range": (50.0, 2000.0),
    },
    "lock_hold_ms": {
        "name": "Shared lock hold duration",
        "default_value": 50.0,
        "unit": "ms",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "concurrency",
        "default_reason": "Critical section hold duration",
        "verification_effect": "Determines acquire wait time under contention",
        "credible_range": (5.0, 300.0),
    },
    "lock_timeout_ms": {
        "name": "Lock acquire timeout",
        "default_value": 100.0,
        "unit": "ms",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "concurrency",
        "default_reason": "Lock acquire timeout",
        "verification_effect": "Trigger for abandoned acquire error",
        "credible_range": (10.0, 500.0),
    },
    "db_pool_size": {
        "name": "Database connection pool capacity",
        "default_value": 10.0,
        "unit": "connections",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "storage",
        "default_reason": "Default database connection pool capacity",
        "verification_effect": "Threshold for connection pool exhaustion",
        "credible_range": (2.0, 100.0),
    },
    "db_demand_connections": {
        "name": "Database active connection demand",
        "default_value": 5.0,
        "unit": "connections",
        "sensitivity": SensitivityLevel.CRITICAL,
        "valid_scope": "storage",
        "default_reason": "Peak concurrency connection demand",
        "verification_effect": "Triggers connection wait queue and timeout",
        "credible_range": (1.0, 80.0),
    },
}


class ModelInput(BaseModel):
    """A fully traceable model parameter input."""
    parameter_id: str
    name: str
    value: Optional[float] = None
    unit: str
    kind: ModelInputKind = ModelInputKind.EXPLICIT_DEFAULT
    source_artifact_id: Optional[str] = None
    source_locator: Optional[str] = None
    extraction_rule: Optional[str] = None
    evidence_backed: bool = False
    confidence: float = 1.0
    uncertainty: Optional[float] = None
    sensitivity: SensitivityLevel = SensitivityLevel.LOW
    verification_effect: str = ""
    assumptions: List[str] = Field(default_factory=list)
    policy_version: str = MODEL_POLICY_VERSION
    default_reason: Optional[str] = None
    valid_scope: Optional[str] = None
    calculation_rationale: Optional[str] = None

    @property
    def display_value(self) -> str:
        """Formatted representation ensuring missing values display UNAVAILABLE."""
        if self.value is None or self.kind == ModelInputKind.UNAVAILABLE:
            return "UNAVAILABLE"
        if isinstance(self.value, float) and self.value.is_integer():
            return f"{int(self.value)} {self.unit}".strip()
        return f"{self.value:.2f} {self.unit}".strip()

    def to_provenance_record(self) -> Any:
        from cauveris.analysis.provenance import create_provenance_record
        return create_provenance_record(
            parameter_id=self.parameter_id,
            value=self.value,
            unit=self.unit,
            provenance=self.kind,
            name=self.name,
            source_artifact=self.source_artifact_id,
            source_locator=self.source_locator,
            calculation_rationale=self.calculation_rationale or self.default_reason,
            confidence=self.confidence,
            uncertainty=self.uncertainty,
            assumptions=self.assumptions,
        )


class SensitivityTrial(BaseModel):
    parameter_id: str
    test_value: float
    unit: str
    repaired: bool
    metric_value: float


class SensitivityAnalysisReport(BaseModel):
    parameter_id: str
    sensitivity: SensitivityLevel
    credible_range: Tuple[float, float]
    trials: List[SensitivityTrial] = Field(default_factory=list)
    outcome_reversal_detected: bool = False
    outcome_variance: float = 0.0
    blocks_model_verification: bool = False
    confidence_penalty: float = 0.0
    notes: List[str] = Field(default_factory=list)


class ModelInputSet(BaseModel):
    """Canonical collection of inputs for a model run with cryptographic hash."""
    model_input_set_id: str
    incident_id: str
    model_id: str
    model_version: str = "2.0"
    inputs: Dict[str, ModelInput] = Field(default_factory=dict)
    input_hash: str
    has_unavailable_critical: bool = False
    sensitivity_reports: Dict[str, SensitivityAnalysisReport] = Field(default_factory=dict)
    verification_blocked: bool = False

    def get_value(self, param_id: str, fallback: Optional[float] = None) -> Optional[float]:
        inp = self.inputs.get(param_id)
        if inp is None or inp.kind == ModelInputKind.UNAVAILABLE:
            return fallback
        return inp.value

    def is_evidence_backed(self, param_id: str) -> bool:
        inp = self.inputs.get(param_id)
        return inp is not None and inp.evidence_backed


class ModelInputBuilder:
    """Constructs a validated, traceable ModelInputSet."""

    def __init__(self, incident_id: str, model_id: str = "cloud_to_robot_twin"):
        self.incident_id = incident_id
        self.model_id = model_id
        self._inputs: Dict[str, ModelInput] = {}

    def add_evidence_input(
        self,
        parameter_id: str,
        value: float,
        unit: str,
        kind: ModelInputKind,
        source_artifact_id: str,
        source_locator: str,
        confidence: float = 1.0,
        uncertainty: Optional[float] = None,
        calculation_rationale: Optional[str] = None,
        extraction_rule: Optional[str] = None,
    ) -> None:
        """Register an evidence-backed parameter input."""
        if parameter_id not in DEFAULT_PARAMETER_POLICIES:
            raise ValueError(
                f"Untracked parameter '{parameter_id}' rejected by validation. "
                f"All parameters must be registered in DEFAULT_PARAMETER_POLICIES."
            )
        norm_val, norm_unit = normalize_value(value, unit)
        policy = DEFAULT_PARAMETER_POLICIES[parameter_id]
        sens = policy.get("sensitivity", SensitivityLevel.MEDIUM)
        ver_eff = policy.get("verification_effect", "")
        name = policy.get("name", parameter_id.replace("_", " ").capitalize())

        self._inputs[parameter_id] = ModelInput(
            parameter_id=parameter_id,
            name=name,
            value=norm_val,
            unit=norm_unit,
            kind=kind,
            source_artifact_id=source_artifact_id,
            source_locator=source_locator,
            extraction_rule=extraction_rule,
            evidence_backed=True,
            confidence=confidence,
            uncertainty=uncertainty,
            sensitivity=sens,
            verification_effect=ver_eff,
            policy_version=MODEL_POLICY_VERSION,
            valid_scope=policy.get("valid_scope"),
            calculation_rationale=calculation_rationale,
        )

    def mark_unavailable(self, parameter_id: str, reason: str = "Not present in evidence artifacts") -> None:
        """Explicitly record a missing parameter as UNAVAILABLE without silent substitution."""
        if parameter_id not in DEFAULT_PARAMETER_POLICIES:
            raise ValueError(
                f"Untracked parameter '{parameter_id}' rejected by validation. "
                f"All parameters must be registered in DEFAULT_PARAMETER_POLICIES."
            )
        policy = DEFAULT_PARAMETER_POLICIES[parameter_id]
        self._inputs[parameter_id] = ModelInput(
            parameter_id=parameter_id,
            name=policy.get("name", parameter_id),
            value=None,
            unit=policy.get("unit", "dimensionless"),
            kind=ModelInputKind.UNAVAILABLE,
            evidence_backed=False,
            confidence=0.0,
            sensitivity=policy.get("sensitivity", SensitivityLevel.MEDIUM),
            verification_effect=policy.get("verification_effect", ""),
            assumptions=[f"Marked UNAVAILABLE: {reason}"],
            policy_version=MODEL_POLICY_VERSION,
            valid_scope=policy.get("valid_scope"),
            calculation_rationale=f"Marked UNAVAILABLE: {reason}",
        )

    def fill_unspecified_with_policy_defaults(self) -> None:
        """Fill parameters not supplied by evidence with explicit, transparent policy defaults."""
        for param_id, policy in DEFAULT_PARAMETER_POLICIES.items():
            if param_id not in self._inputs:
                self._inputs[param_id] = ModelInput(
                    parameter_id=param_id,
                    name=policy["name"],
                    value=policy["default_value"],
                    unit=policy["unit"],
                    kind=ModelInputKind.EXPLICIT_DEFAULT,
                    evidence_backed=False,
                    confidence=0.7,
                    sensitivity=policy["sensitivity"],
                    verification_effect=policy["verification_effect"],
                    default_reason=policy["default_reason"],
                    valid_scope=policy["valid_scope"],
                    assumptions=[f"Assumed explicit model default: {policy['default_reason']}"],
                    policy_version=MODEL_POLICY_VERSION,
                )

    def build(self) -> ModelInputSet:
        # Check if critical parameters are unavailable
        has_unavailable_critical = any(
            inp.kind == ModelInputKind.UNAVAILABLE and inp.sensitivity == SensitivityLevel.CRITICAL
            for inp in self._inputs.values()
        )

        # Compute deterministic hash of inputs
        content_repr = json.dumps(
            {k: self._inputs[k].model_dump() for k in sorted(self._inputs.keys())},
            sort_keys=True,
            default=str,
        )
        input_hash = hashlib.sha256(content_repr.encode("utf-8")).hexdigest()[:16]
        input_set_id = f"inputs_{self.incident_id}_{input_hash}"

        return ModelInputSet(
            model_input_set_id=input_set_id,
            incident_id=self.incident_id,
            model_id=self.model_id,
            inputs=self._inputs,
            input_hash=input_hash,
            has_unavailable_critical=has_unavailable_critical,
            verification_blocked=has_unavailable_critical,
        )

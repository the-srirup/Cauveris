"""
The Cauveris analysis layer.

This package turns a raw incident bundle into a model of the system that
produced the incident:

``evidence``      - bundle discovery and normalisation (config, logs, metrics,
                    traces, MCAP recordings, deployments).
``statistics``    - real estimators: distributions, Welch/Mann-Whitney/KS
                    tests, Cohen's d, change-point detection.
``model``         - a discrete-event simulation of the perception pipeline and
                    a bounded global calibration of its parameters.
``system_model``  - the incident model that binds the evidence to parameters,
                    budgets, change points and robot kinematics.

Nothing in this package knows about a specific incident: every number is
derived from the bundle that was handed to it.
"""

from __future__ import annotations

from .evidence import (
    ConfigChange,
    DeploymentEvent,
    EvidenceBundle,
    LogRecord,
    MetricSample,
    RecordingMessage,
    Span,
    flatten_config,
    parse_timestamp,
)
from .model import (
    LatencyCalibration,
    SimulationOutcome,
    TwinParameters,
    calibrate_latency_model,
    simulate_pipeline,
)
from .statistics import (
    ChangePoint,
    Distribution,
    cohens_d,
    detect_change_point,
    distribution,
    ks_two_sample,
    linear_fit,
    mann_whitney,
    percentile,
    percentile_rank,
    welch_t_test,
)
from .system_model import (
    ConfigDelta,
    Kinematics,
    ParameterRole,
    SafetyBudget,
    SystemModel,
    arrival_rate_evidence,
    build_system_model,
    classify_parameter,
    get_system_model,
)

__all__ = [
    # evidence
    "ConfigChange",
    "DeploymentEvent",
    "EvidenceBundle",
    "LogRecord",
    "MetricSample",
    "RecordingMessage",
    "Span",
    "flatten_config",
    "parse_timestamp",
    # statistics
    "ChangePoint",
    "Distribution",
    "cohens_d",
    "detect_change_point",
    "distribution",
    "ks_two_sample",
    "linear_fit",
    "mann_whitney",
    "percentile",
    "percentile_rank",
    "welch_t_test",
    # model
    "LatencyCalibration",
    "SimulationOutcome",
    "TwinParameters",
    "calibrate_latency_model",
    "simulate_pipeline",
    # system model
    "ConfigDelta",
    "Kinematics",
    "ParameterRole",
    "SafetyBudget",
    "SystemModel",
    "arrival_rate_evidence",
    "build_system_model",
    "classify_parameter",
    "get_system_model",
]

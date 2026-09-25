"""
Temporal Causality Analysis package for Cauveris.

This package detects when "time itself" becomes an anomaly in distributed
system events — beyond simple clock synchronization.

Key modules:
- ``causality``: Temporal anomaly and violation detection
- ``clock``: Clock domain analysis and skew estimation
- ``loops``: Time loop detection in causal graphs
- ``pattern``: Anomaly classification and clustering
- ``integration``: ``TemporalAnalyzer`` orchestration
- ``evidence``: Evidence model and extraction from timeline events

Public API:

>>> from cauveris.temporal import TemporalAnalyzer
>>> result = TemporalAnalyzer().analyze_incident(incident, bundle_path)
>>> print(result["is_time_anomalous"])

"""
from __future__ import annotations

from cauveris.temporal.causality import CausalityViolation, CausalEdge, infer_causal_edges
from cauveris.temporal.clock import ClockAnalysisResult, ClockDomain, ClockStatus, ClockSkewAnalyzer, DomainClockModel
from cauveris.temporal.evidence import CausalityProvenance, RawSignalExtractor, TemporalEvidence, TimestampKind, extract_from_timeline
from cauveris.temporal.integration import TemporalAnalyzer, TemporalAnalysisResult, analyze_incident_timeline
from cauveris.temporal.loops import TimeLoop, TimeLoopDetector
from cauveris.temporal.pattern import AnomalyType, AnomalyPatternRecognizer, TemporalAnomaly
from cauveris.temporal.config import TemporalConfig, TolerancePolicy

__all__ = [
    # Main orchestrator
    "TemporalAnalyzer",
    "TemporalAnalysisResult",
    "analyze_incident_timeline",

    # Evidence extraction
    "extract_from_timeline",
    "RawSignalExtractor",
    "TemporalEvidence",
    "TimestampKind",
    "CausalityProvenance",

    # Causality
    "CausalityViolation",
    "CausalEdge",
    "infer_causal_edges",

    # Clock analysis
    "ClockSkewAnalyzer",
    "ClockAnalysisResult",
    "ClockDomain",
    "ClockStatus",
    "DomainClockModel",

    # Time loops
    "TimeLoop",
    "TimeLoopDetector",

    # Pattern recognition
    "AnomalyType",
    "TemporalAnomaly",
    "AnomalyPatternRecognizer",

    # Config
    "TemporalConfig",
    "TolerancePolicy",
]

# Version tag for the temporal module
__version__ = "0.1.0"
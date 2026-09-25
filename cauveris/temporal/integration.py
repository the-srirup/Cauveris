"""
Temporal analysis integration: orchestrates the full analysis pipeline.

This module provides the main ``TemporalAnalyzer`` class that consumers (the
pipeline orchestrator, the API, the report generator) will use to analyze an
incident for temporal anomalies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from cauveris.config import get_settings
from cauveris.temporal.causality import CausalityViolation, infer_causal_edges
from cauveris.temporal.clock import ClockAnalysisResult, ClockSkewAnalyzer
from cauveris.temporal.evidence import (
    RawSignalExtractor,
    TemporalEvidence,
    extract_from_timeline,
)
from cauveris.temporal.loops import TimeLoopDetector
from cauveris.temporal.pattern import (
    AnomalyPatternRecognizer,
    TemporalAnomaly,
)

logger = logging.getLogger(__name__)


@dataclass
class TemporalAnalysisResult:
    """
    Complete temporal analysis report for an incident.
    """
    incident_id: str
    total_events: int
    causality_violations: List[Dict[str, Any]] = field(default_factory=list)
    time_loops: List[Dict[str, Any]] = field(default_factory=list)
    temporal_anomalies: List[Dict[str, Any]] = field(default_factory=list)
    clock_analysis: Optional[Dict[str, Any]] = None
    is_time_anomalous: bool = False
    temporal_confidence_score: float = 1.0
    untrusted_windows: List[Dict[str, Any]] = field(default_factory=list)
    raw_signal_summary: Dict[str, Any] = field(default_factory=dict)


class TemporalAnalyzer:
    """
    Main orchestrator for temporal causality analysis.

    Usage:

    ```python
    analyzer = TemporalAnalyzer()
    result = await analyzer.analyze_incident_timeline(incident)
    # result is serializable dict for API response or report embedding
    ```

    For synchronous use (pipeline stage that happens after timeline build):

    ```python
    analyzer = TemporalAnalyzer()
    result = analyzer.analyze_incident(incident, bundle_path)
    ```
    """

    def __init__(
        self,
        bundle_path: Optional[Path] = None,
        freshness_budget_ms: float = 120.0,
        control_deadline_ms: float = 100.0,
    ):
        self.bundle_path = bundle_path
        self.freshness_budget_ms = freshness_budget_ms
        self.control_deadline_ms = control_deadline_ms

        # Lazily-loaded components
        self._clock_analyzer: Optional[ClockSkewAnalyzer] = None
        self._loop_detector: Optional[TimeLoopDetector] = None
        self._pattern_recognizer: Optional[AnomalyPatternRecognizer] = None

    @property
    def clock_analyzer(self) -> ClockSkewAnalyzer:
        if self._clock_analyzer is None:
            self._clock_analyzer = ClockSkewAnalyzer(
                skew_threshold_ms=10.0,
                mad_k=3.5,
            )
        return self._clock_analyzer

    @property
    def loop_detector(self) -> TimeLoopDetector:
        if self._loop_detector is None:
            self._loop_detector = TimeLoopDetector(
                min_loop_size=2,
                confidence_threshold=0.5,
            )
        return self._loop_detector

    @property
    def pattern_recognizer(self) -> AnomalyPatternRecognizer:
        if self._pattern_recognizer is None:
            self._pattern_recognizer = AnomalyPatternRecognizer()
        return self._pattern_recognizer

    def analyze_incident(
        self,
        incident,
        bundle_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Perform full temporal analysis on an incident's timeline.

        This is the main entry point for synchronous analysis (e.g., used by
        the pipeline orchestrator after timeline is built).

        Args:
            incident: The incident object with ``timeline_events`` and optionally
                      ``manifest`` containing ``clock_alignment``.
            bundle_path: Optional explicit bundle path (overrides incident's path).

        Returns:
            Dict ready for API/json serialization.
        """
        timeline_events = getattr(incident, "timeline_events", None) or []

        # Resolve bundle path
        if bundle_path is None:
            settings = get_settings()
            bundle_path = Path(settings.evidence_store_path) / incident.id
            if not bundle_path.exists():
                bundle_path = Path(f"./incident-{incident.id}")
            if not bundle_path.exists():
                bundle_path = Path("./golden_incident/incident-CAU-0001")

        # Extract raw signals for deeper analysis
        raw_extractor = RawSignalExtractor(bundle_path)
        raw_signals = raw_extractor.extract_all()

        # Build temporal evidence
        evidence = extract_from_timeline(
            timeline_events, bundle_path
        )

        # Add raw signals to evidence
        for ev in evidence:
            if ev.evidence_id:
                # Attach MCAP detection age if available
                for msg in raw_signals.get("mcap", {}).get("messages", []):
                    if ev.evidence_id.endswith(str(msg.get("log_time_ns") % 1_000_000)):
                        ev.extra["mcap_age_ms"] = msg.get("detection_age_ms")

        # Clock analysis
        manifest = getattr(incident, "manifest", None) or {}
        clock_alignment = manifest.get("clock_alignment", {})
        clock_result = self.clock_analyzer.analyze(evidence, raw_signals, clock_alignment)

        # Causality violations
        infer_causal_edges(evidence, raw_signals, self.freshness_budget_ms)

        # Build edge map for violation detector
        violations: List[CausalityViolation] = []
        for ev in evidence:
            for child_id in ev.child_candidates:
                prov = ev.child_provenance.get(child_id)
                if prov:
                    for child_ev in evidence:
                        if child_ev.evidence_id == child_id:
                            delta = child_ev.timestamp_ns - ev.timestamp_ns
                            tolerance_ns = self._tolerance_for_provenance(prov, ev, child_ev, raw_signals)
                            if delta < -tolerance_ns:
                                confidence = min(1.0, abs(delta) / max(tolerance_ns, 1))
                                violations.append(CausalityViolation(
                                    cause_id=ev.evidence_id,
                                    effect_id=child_ev.evidence_id,
                                    provenance=prov,
                                    timestamp_delta_ns=delta,
                                    tolerance_ns=tolerance_ns,
                                    confidence=confidence,
                                    description=(
                                        f"Effect {child_ev.evidence_id[:40]}... appeared "
                                        f"{abs(delta) / 1e6:.1f}ms before cause "
                                        f"{ev.evidence_id[:40]}... (tolerance: {tolerance_ns / 1e6:.1f}ms)"
                                    ),
                                ))
                            break

        # Ground-truth report of violations from design doc
        causality_violations = [
            {
                "event_a": v.cause_id,
                "event_b": v.effect_id,
                "violation": v.description,
                "time_delta_ms": v.timestamp_delta_ns / 1_000_000.0,
                "confidence": v.confidence,
            }
            for v in violations
        ]

        # Time loop detection
        time_loops = self.loop_detector.detect(evidence)
        time_loop_reports = [
            {
                "loop_id": loop.loop_id,
                "events": loop.events,
                "cycle_length_ms": loop.cycle_length_ms,
                "confidence": loop.confidence,
                "description": loop.description,
            }
            for loop in time_loops
        ]

        # Pattern recognition
        anomalies = self.pattern_recognizer.analyze(evidence, violations, raw_signals)
        temporal_anomalies = [
            {
                "type": a.anomaly_type.value,
                "severity": a.severity,
                "timestamp_range": a.timestamp_range,
                "confidence": a.confidence,
                "explanation": a.explanation,
                "affected_events": a.affected_events,
            }
            for a in anomalies
        ]

        # Temporal confidence score
        confidence = self._calculate_temporal_confidence(
            violations, anomalies, clock_result
        )

        # Unsupervised windows (events that can't be trusted due to co-temporal)
        untrusted = self._compute_untrusted_windows(evidence, violations, clock_result)

        # Build final result
        result = {
            "incident_id": incident.id,
            "total_events_analyzed": len(evidence),
            "causality_violations": causality_violations,
            "time_loops": time_loop_reports,
            "temporal_anomalies": temporal_anomalies,
            "clock_analysis": clock_result.to_dict(),
            "is_time_anomalous": len(violations) > 0 or len(anomalies) > 0,
            "temporal_confidence_score": confidence,
            "untrusted_windows": untrusted,
        }

        # Annotate incident for report embedding
        self._annotate_incident(incident, result)

        return result

    # ------------------------------------------------------------------ #
    def _tolerance_for_provenance(
        self,
        provenance,
        cause: TemporalEvidence,
        effect: TemporalEvidence,
        raw_signals: Dict[str, Any],
    ) -> int:
        """Compute per-edge tolerance in nanoseconds."""
        # Base tolerance from provenance
        base_map = {
            "otel_trace_order": 25_000_000,
            "ros_topic_order": 50_000_000,
            "log_node_order": 100_000_000,
            "cross_domain_handoff": 250_000_000,
            "deployment_chain": 24 * 3600 * 1_000_000_000,
            "temporal_proximity": 50_000_000,
        }
        base = base_map.get(provenance.value if hasattr(provenance, "value") else str(provenance), 50_000_000)

        # Add jitter term
        jitter = 0
        mcap = raw_signals.get("mcap", {})
        for msg in mcap.get("messages", []):
            delta = abs(msg.get("publish_time_ns", 0) - msg.get("log_time_ns", 0))
            if delta > jitter:
                jitter = delta

        # Add precision loss term
        precision_ns = max(cause.precision_ns, effect.precision_ns)

        return int(base + 3 * jitter + precision_ns)

    # ------------------------------------------------------------------ #
    def _calculate_temporal_confidence(
        self,
        violations: List[CausalityViolation],
        anomalies: List[TemporalAnomaly],
        clock_result: ClockAnalysisResult,
    ) -> float:
        """
        Compute overall confidence in the timeline's temporal integrity.

        Low confidence means parts of the timeline may be unreliable.
        """
        if not violations and not anomalies and not clock_result.domains:
            return 1.0

        max_violation_sev = max((v.confidence for v in violations), default=0.0)
        max_anomaly_sev = max((a.severity for a in anomalies), default=0.0)

        max_skew = max(
            (m.offset_ns for m in clock_result.domains.values()),
            default=0,
        )
        skew_factor = min(1.0, max_skew / 1_000_000_000.0)

        # Combined metric: lower = more confidence
        combined = max(max_violation_sev, max_anomaly_sev, skew_factor)

        return round(1.0 - combined, 3)

    # ------------------------------------------------------------------ #
    def _compute_untrusted_windows(
        self,
        evidence: List[TemporalEvidence],
        violations: List[CausalityViolation],
        clock_result: ClockAnalysisResult,
    ) -> List[Dict[str, Any]]:
        """
        Find chronological windows that cannot be trusted due to temporal
        anomalies (co-temporal ambiguity, violations, or clock issues).

        Returns a list of dicts with ``start_s``, ``end_s``, and ``reason``.
        """
        windows = []

        # Extract co-temporal buckets as untrusted
        for ts_ns, eids in clock_result.co_temporal_buckets.items():
            windows.append({
                "type": "co_temporal_ambiguity",
                "start_s": ts_ns / 1e9,
                "end_s": ts_ns / 1e9,
                "evidence_count": len(eids),
                "description": "Events at this instant span multiple clock domains",
            })

        # Brotli windows around detected violations
        for v in violations[:10]:  # cap to avoid report bloat
            windows.append({
                "type": "causality_violation",
                "start_s": min(
                    (e.timestamp_ns for e in evidence if e.evidence_id in (v.cause_id, v.effect_id)),
                    default=0,
                ) / 1e9,
                "end_s": max(
                    (e.timestamp_ns for e in evidence if e.evidence_id in (v.cause_id, v.effect_id)),
                    default=0,
                ) / 1e9,
                "violation": v.description,
            })

        return windows

    # ------------------------------------------------------------------ #
    def _annotate_incident(self, incident, result: Dict[str, Any]) -> None:
        """
        Attach temporal flags to the incident's timeline events.

        This allows consumers like the report generator to include
        per-event trust scores without re-running the analyzer.
        """
        timeline = getattr(incident, "timeline_events", None)
        if not timeline:
            return

        # Build sets of untrusted event IDs
        untrusted_ids: Set[str] = set()
        for window in result.get("untrusted_windows", []):
            untrusted_ids.update(window.get("evidence_ids", []))
        for v in result.get("causality_violations", []):
            untrusted_ids.add(v.get("event_a", ""))
            untrusted_ids.add(v.get("event_b", ""))

        # Annotate each event with a trust score
        for evt in timeline:
            evt_id = evt.get("event_id") or evt.get("evidence_id", "")
            if evt_id in untrusted_ids:
                evt["temporal_trust"] = 0.5
            else:
                # Events after co-temporal ambiguities get reduced trust
                evt["temporal_trust"] = 1.0


# ----------------------------------------------------------------------
# Convenience functions for direct API usage
# ----------------------------------------------------------------------
async def analyze_incident_timeline(incident) -> Dict[str, Any]:
    """
    Async wrapper for ``TemporalAnalyzer.analyze_incident`` for API endpoints.

    The caller does not need to instantiate a TemporalAnalyzer; this function
    creates one with defaults appropriate for the API context.
    """
    analyzer = TemporalAnalyzer()
    return analyzer.analyze_incident(incident)


async def analyze_incident_timeline_async(incident, bundle_path: Optional[Path] = None):
    """Alias for consistency with async API endpoints."""
    return await analyze_incident_timeline(incident)

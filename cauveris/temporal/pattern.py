"""
Anomaly pattern recognition: detect patterns of temporal irregularities.

This module classifies the various ways time can go "wrong" in a distributed
system:

* **Clock Skew**: Two domains disagree on what "now" is, leading to causal
  order inversion for events that are actually simultaneous or slightly
  reordered.
* **Timestamp Inversion**: A sequence of events (e.g., log lines) shows
  descending wall-clock times, which can mean a clock was reset or logs
  were replayed backwards.
* **Causality Reversal**: A child event is timestamped before its parent.
  This is often a symptom of bug #1 (clock skew) but can also indicate a
  genuine asynchronous ordering bug (e.g., a race condition printed in logs
  out of order).
* **Co-Temporal Ambiguity**: Two events from different domains are logged at
  nanosecond-identical times, making causal ordering strictly undecidable from
  timestamps alone. The analyzer must flag these as untrusted.
* **Timestamp Precision Loss**: A coarse-granularity timestamp source (e.g.,
  syslog's second-precision) cannot distinguish events that occur within a
  second of each other.
* **Domain Mixing**: A single log file mixes time sources (wall-clock and
  monotonic), corrupting the chronological sequence.

The analyzer clusters anomalies by affected events to identify systemic
issues.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Set, Tuple

from cauveris.temporal.causality import CausalityViolation

logger = logging.getLogger(__name__)


class AnomalyType(str, Enum):
    """
    Types of temporal anomalies that can be detected.
    """
    CLOCK_SKEW = "clock_skew"
    CLOCK_DESYNC = "clock_desync"
    TIMESTAMP_INVERSION = "timestamp_inversion"
    CAUSALITY_REVERSAL = "causality_reversal"
    TIME_LOOP = "time_loop"
    CO_TEMPORAL_AMBIGUITY = "co_temporal_ambiguity"
    LATENCY_BUDGET_BREACH = "latency_budget_breach"
    TIMESTAMP_PRECISION_LOSS = "timestamp_precision_loss"
    CLOCK_DOMAIN_MIXING = "clock_domain_mixing"
    EVENT_REORDERING = "event_reordering"
    TEMPORAL_ANOMALY = "temporal_anomaly"


@dataclass
class TemporalAnomaly:
    """
    A detected temporal irregularity.
    """
    anomaly_type: AnomalyType
    severity: float  # 0..1, higher = more severe
    affected_events: List[str]
    timestamp_range: Tuple[float, float]  # (start, end) seconds since epoch
    confidence: float  # 0..1, how sure we are about this finding
    explanation: str
    evidence_ids: List[str] = field(default_factory=list)


class AnomalyPatternRecognizer:
    """
    Recognize patterns in temporal anomalies and cluster findings.

    The recognizer applies several heuristics to find systematic
    temporal issues (e.g., an entire domain is mis-timed, or a particular
    source file has monotonicity problems).
    """

    def __init__(self):
        self.anomalies: List[TemporalAnomaly] = []

    def analyze(
        self,
        evidence: List[Any],  # List[TemporalEvidence]
        violations: List[CausalityViolation],
        raw_signals: Dict[str, Any],
    ) -> List[TemporalAnomaly]:
        """
        Run all pattern detectors and return aggregated anomalies.

        Args:
            evidence: The temporal evidence list
            violations: Causality violations detected
            raw_signals: Raw signals dict from RawSignalExtractor

        Returns
        -------
        List[TemporalAnomaly]
            All detected anomalies, clustered and sorted by severity.
        """
        self.anomalies = []

        self._detect_latency_budged_breaches(evidence, raw_signals)
        self._detect_timestamp_inversions(evidence)
        self._detect_co_temporal_ambiguity(evidence, raw_signals)
        self._detect_domain_mixing(evidence, raw_signals)
        self._detect_timestamp_precision_loss(evidence, raw_signals)

        # Add violations as CAUSALITY_REVERSAL anomalies
        for v in violations:
            self.anomalies.append(TemporalAnomaly(
                anomaly_type=AnomalyType.CAUSALITY_REVERSAL,
                severity=min(1.0, v.confidence),
                affected_events=[v.cause_id, v.effect_id],
                timestamp_range=(
                    v.cause.timestamp_ns / 1e9 if hasattr(v, 'cause_time') else 0,
                    v.effect.timestamp_ns / 1e9 if hasattr(v, 'effect_time') else 0,
                ),
                confidence=v.confidence,
                explanation=v.description,
                evidence_ids=[v.cause_id, v.effect_id],
            ))

        # Cluster overlapping anomalies
        self.anomalies = self._cluster_anomalies(self.anomalies)

        return self.anomalies

    # ------------------------------------------------------------------ #
    def _detect_latency_budged_breaches(
        self, evidence: List[Any], raw_signals: Dict[str, Any]
    ) -> None:
        """
        Find events where observed latency exceeded the freshness budget.

        The MCAP messages carry ``detection_age_ms`` computed from
        ``log_time - header.stamp_ns``; this is a direct measurement of the
        staleness of the perception data.
        """
        mcap = raw_signals.get("mcap", {})
        for msg in mcap.get("messages", []):
            if msg.get("detection_age_ms") is not None:
                age = msg["detection_age_ms"]
                if age > 120.0:
                    self.anomalies.append(TemporalAnomaly(
                        anomaly_type=AnomalyType.LATENCY_BUDGET_BREACH,
                        severity=min(1.0, age / 200.0),  # caps at 1.0 for 200+ ms
                        affected_events=[msg.get("topic", "unknown")],
                        timestamp_range=(msg["log_time_ns"] / 1e9, msg["log_time_ns"] / 1e9),
                        confidence=1.0,
                        explanation=f"Detection age {age:.1f}ms exceeded 120ms freshness budget",
                    ))

    # ------------------------------------------------------------------ #
    def _detect_timestamp_inversions(self, evidence: List[Any]) -> None:
        """
        Find events that appear out of order within a single source file.

        This uses the intrinsic sequence (line number for logs, message index
        for MCAP) to determine expected order, then checks against wall-clock.
        """
        by_file: Dict[str, List[Any]] = {}
        for ev in evidence:
            source = ev.source
            by_file.setdefault(source, []).append(ev)

        for source, events in by_file.items():
            # Check jsonl logs for inversions
            jsonl_events = [e for e in events if e.source_type == "jsonl_log"]
            if jsonl_events:
                prev_ts = None
                for ev in jsonl_events:
                    ts = ev.timestamp_ns
                    if prev_ts is not None and ts < prev_ts:
                        self.anomalies.append(TemporalAnomaly(
                            anomaly_type=AnomalyType.TIMESTAMP_INVERSION,
                            severity=0.7,
                            affected_events=[ev.evidence_id],
                            timestamp_range=(ts / 1e9, prev_ts / 1e9),
                            confidence=0.8,
                            explanation=f"Log inversion: {ev.source}:{ev.extra.get('attributes', {}).get('line_number', '?')} timestamped before prior line",
                        ))
                    prev_ts = ts

    # ------------------------------------------------------------------ #
    def _detect_co_temporal_ambiguity(
        self, evidence: List[Any], raw_signals: Dict[str, Any]
    ) -> None:
        """
        Flag events that share identical timestamps across different clock domains.

        The MCAP extractor returned buckets of events at identical log_time.
        These are genuinely co-temporal, so the analyzer cannot establish
        causal order from timestamps alone for them.
        """
        mcap = raw_signals.get("mcap", {})
        buckets = mcap.get("co_temporal_ambiguities", {})

        for ts_ns, event_ids in buckets.items():
            if len(event_ids) > 1:
                # Map IDs back to evidence for domain info
                domains = set()
                for e in evidence:
                    if e.evidence_id in event_ids:
                        domains.add(e.clock_domain)
                if len(domains) > 1:
                    self.anomalies.append(TemporalAnomaly(
                        anomaly_type=AnomalyType.CO_TEMPORAL_AMBIGUITY,
                        severity=0.6,
                        affected_events=event_ids[:10],  # cap for report size
                        timestamp_range=(ts_ns / 1e9, ts_ns / 1e9),
                        confidence=1.0,
                        explanation=f"Events at {ts_ns}ns span domains {list(domains)} - causal order undecidable from timestamps",
                    ))

        # EStop + Safety at same time (special case from MCAP)
        for estop in mcap.get("estop_safety_co_temporal", []):
            t = estop["time_ns"]
            topics = estop["topics"]
            self.anomalies.append(TemporalAnomaly(
                anomaly_type=AnomalyType.CO_TEMPORAL_AMBIGUITY,
                severity=0.8,
                affected_events=topics,
                timestamp_range=(t / 1e9, t / 1e9),
                confidence=1.0,
                explanation=f"E-stop command and safety status logged at same instant - order undecidable (topics: {topics})",
            ))

    # ------------------------------------------------------------------ #
    def _detect_domain_mixing(self, evidence: List[Any], raw_signals: Dict[str, Any]) -> None:
        """
        Detect logs that mix different timestamp semantics in a single file.

        The system.log contains both an ISO8601 timestamp (e.g.,
        ``2026-09-20T10:29:50Z``) AND a kernel monotonic bracket (e.g.,
        ``[10421.11]``). These refer to different clock domains.
        """
        sys_log = raw_signals.get("system_log", {})
        brackets = sys_log.get("monotonic_brackets", [])
        mixed = sys_log.get("mixed_domain_entries", 0)

        if brackets and mixed > 0:
            # Extract timestamps from brackets for precision loss check
            precision_ns = 1_000_000_000  # seconds -> nanoseconds loss
            self.anomalies.append(TemporalAnomaly(
                anomaly_type=AnomalyType.CLOCK_DOMAIN_MIXING,
                severity=0.5,
                affected_events=[],
                timestamp_range=(0, 0),
                confidence=0.9,
                explanation=f"system.log mixes wall-clock and kernel monotonic timestamps ({mixed} mixed entries, {len(brackets)} brackets found)",
            ))

        # Second precision check
        precision_loss = sys_log.get("second_precision_samples", 0)
        if precision_loss > 0:
            self.anomalies.append(TemporalAnomaly(
                anomaly_type=AnomalyType.TIMESTAMP_PRECISION_LOSS,
                severity=precision_loss / 100.0,  # scale by count
                affected_events=[],
                timestamp_range=(0, 0),
                confidence=0.8,
                explanation=f"system.log timestamps have second precision only ({precision_loss} samples) - sub-ms ordering uncertain",
            ))

    # ------------------------------------------------------------------ #
    def _detect_timestamp_precision_loss(
        self, evidence: List[Any], raw_signals: Dict[str, Any]
    ) -> None:
        """
        Per-source file, report when timestamp precision is insufficient to
        order events that are close together.

        Uses ``RawSignalExtractor.extract_csv_signals`` output.
        """
        csv_signals = raw_signals.get("csv_metrics", {})
        for fname, data in csv_signals.get("column_precision", {}).items():
            if data.get("second_only_samples", 0) > 0 and data.get("microsecond_samples", 0) == 0:
                self.anomalies.append(TemporalAnomaly(
                    anomaly_type=AnomalyType.TIMESTAMP_PRECISION_LOSS,
                    severity=0.3,
                    affected_events=[],
                    timestamp_range=(0, 0),
                    confidence=0.7,
                    explanation=f"{fname} has second-precision timestamps only",
                ))

    # ------------------------------------------------------------------ #
    def _cluster_anomalies(self, anomalies: List[TemporalAnomaly]) -> List[TemporalAnomaly]:
        """
        Simple clustering: merge anomalies that affect the same events.

        Returns a de-duplicated list sorted by severity.
        """
        if not anomalies:
            return []

        clustered: List[TemporalAnomaly] = []
        for anom in anomalies:
            merged = False
            for existing in clustered:
                # Overlap in affected events
                overlap = set(anom.affected_events) & set(existing.affected_events)
                if overlap:
                    existing.severity = max(existing.severity, anom.severity)
                    existing.confidence = (existing.confidence + anom.confidence) / 2.0
                    merged = True
                    break
            if not merged:
                clustered.append(anom)

        return sorted(clustered, key=lambda a: a.severity, reverse=True)
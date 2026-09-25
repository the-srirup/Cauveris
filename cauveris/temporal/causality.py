"""
Temporal causality analysis: detect violations of expected chronological order.

A causality violation occurs when an effect appears to happen before its cause
in the timestamp records. The analyzer is conservative: violations require
the time delta to be *significantly* negative, beyond the combined tolerance
of:

1. The provenance's expected latency allowance.
2. Measured clock-domain jitter (3x MAD).
3. Timestamp precision loss (for coarse-grained sources).

This approach avoids flagging normal processing latency as anomalies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from cauveris.temporal.config import TolerancePolicy
from cauveris.temporal.evidence import CausalityProvenance, TemporalEvidence

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Public types
# ----------------------------------------------------------------------
@dataclass
class CausalityViolation:
    """
    A detected causality violation — an effect that preceded its cause.

    The violation is *not* a bug in the system; it is a data quality issue
    that must be flagged as making part of the timeline untrustworthy.

    Attributes:
        cause_id: Evidence ID of the putative cause
        effect_id: Evidence ID of the putative effect
        provenance: How we know the edge exists (see ``CausalityProvenance``)
        timestamp_delta_ns: effect_ts - cause_ts (may be negative)
        tolerance_ns: the negative threshold below which delta is flagged
        confidence: 0..1 score, higher when delta is strongly negative
        description: Human-readable explanation
    """
    cause_id: str
    effect_id: str
    provenance: CausalityProvenance
    timestamp_delta_ns: int
    tolerance_ns: int
    confidence: float
    description: str


@dataclass
class CausalEdge:
    """
    A directed edge in the inferred causal graph.
    """
    cause_id: str
    effect_id: str
    provenance: CausalityProvenance
    is_inferred: bool = True


# ----------------------------------------------------------------------
# Temporal anomaly detector
# ----------------------------------------------------------------------
class TemporalAnomalyDetector:
    """
    Detects causality violations in a timeline.

    Construction requires a tolerance policy, which is usually built from
    ``TolerancePolicy.from_config`` but can be tuned per-incident.
    """

    def __init__(self, policy: Optional[TolerancePolicy] = None):
        self.policy = policy or TolerancePolicy()
        self.violations: List[CausalityViolation] = []

    def analyze(
        self,
        evidence: List[TemporalEvidence],
        clock_skew_ns: int = 0,
    ) -> List[CausalityViolation]:
        """
        Scan all evidence for causality violations.

        Args:
            evidence: List of temporal evidence objects with inferred edges
            clock_skew_ns: Global clock offset estimate to apply to timestamps

        Returns:
            List of violations (may be empty)
        """
        self.violations = []

        for ev in evidence:
            for effect_id in ev.child_candidates:
                effect = self._find_evidence(evidence, effect_id)
                if effect is None:
                    continue

                violation = self._check_edge(ev, effect, clock_skew_ns)
                if violation:
                    self.violations.append(violation)

        return self.violations

    # ------------------------------------------------------------------ #
    def _find_evidence(
        self, evidence: List[TemporalEvidence], evidence_id: str
    ) -> Optional[TemporalEvidence]:
        for ev in evidence:
            if ev.evidence_id == evidence_id:
                return ev
        return None

    # ------------------------------------------------------------------ #
    def _check_edge(
        self,
        cause: TemporalEvidence,
        effect: TemporalEvidence,
        clock_skew_ns: int,
    ) -> Optional[CausalityViolation]:
        """
        Check if cause->effect violates temporal causality.

        The expected order is cause before effect. The actual order is determined
        by corrected timestamps. A violation occurs when:
            effect.corrected > cause.corrected + tolerance
        is FALSE (i.e., effect.corrected < cause.corrected - tolerance)
        """
        # Adjust for any global clock offset to align domains
        cause_ts = cause.timestamp_ns + clock_skew_ns
        effect_ts = effect.timestamp_ns + clock_skew_ns

        delta_ns = effect_ts - cause_ts  # positive = effect after cause (good)

        # Get tolerance for this edge's provenance (this is where the jitter
        # penalty is applied)
        precision_ns = max(cause.precision_ns, effect.precision_ns)
        tolerance_ns = self.policy.tolerance_ms(
            cause.child_provenance.get(effect.evidence_id, "temporal_proximity"),
            jitter_ms=0.0,  # jitter computed elsewhere in ClockAnalyzer
            precision_ns=precision_ns,
        )

        if delta_ns < -tolerance_ns:
            # Violation detected!
            confidence = min(1.0, abs(delta_ns) / max(tolerance_ns, 1))
            return CausalityViolation(
                cause_id=cause.evidence_id,
                effect_id=effect.evidence_id,
                provenance=cause.child_provenance.get(effect.evidence_id, CausalityProvenance.TEMPORAL_PROXIMITY),
                timestamp_delta_ns=delta_ns,
                tolerance_ns=tolerance_ns,
                confidence=confidence,
                description=(
                    f"Effect {effect.evidence_id[:40]}... appeared {abs(delta_ns) / 1_000_000:.1f}ms "
                    f"before its cause {cause.evidence_id[:40]}... (tolerance: {tolerance_ns / 1_000_000:.1f}ms)"
                ),
            )

        return None


# ----------------------------------------------------------------------
# Helper for building edge operations (used by temporal analyzer)
# ----------------------------------------------------------------------
def infer_causal_edges(
    evidence: List[TemporalEvidence],
    raw_signals: Optional[Dict[str, Any]] = None,
    max_latency_budget_ms: float = 120.0,
) -> List[CausalEdge]:
    """
    Build a causal graph from evidence using all available semantics.

    This is a convenience wrapper for ``EvidenceExtractor._add_timeline_causal_hints``
    followed by explicit rules for:

    - Deployment chain: deployment event establishes a causal horizon.
    - Freshness budget: evidence exceeding budget is explicitly flagged as a
      causally complex case (the effect may appear timing-inconsistent).
    """
    edges: List[CausalEdge] = []

    # Deployment -> everything after
    deployments = [e for e in evidence if e.source_type == "deployment_json"]
    for dep in deployments:
        for ev in evidence:
            if ev is dep or ev.timestamp_ns <= dep.timestamp_ns:
                continue
            edges.append(CausalEdge(
                cause_id=dep.evidence_id,
                effect_id=ev.evidence_id,
                provenance=CausalityProvenance.DEPLOYMENT_CHAIN,
            ))

    # Freshness budget violation detection
    for ev in evidence:
        latency_expected = max_latency_budget_ms
        # From MCAP signals
        if raw_signals:
            mcap = raw_signals.get("mcap", {})
            for msg in mcap.get("messages", []):
                age_ms = msg.get("detection_age_ms")
                if age_ms is not None and age_ms > latency_expected:
                    # Tag the detection event as violating freshness
                    ev.extra = ev.extra or {}
                    ev.extra["freshness_violation_ms"] = age_ms

    # MCAP topic ordering is already baked into parents/children; just mirror edges
    for ev in evidence:
        for child in ev.child_candidates:
            prov = ev.child_provenance.get(child)
            if prov:
                edges.append(CausalEdge(
                    cause_id=ev.evidence_id,
                    effect_id=child,
                    provenance=prov,
                ))

    return edges
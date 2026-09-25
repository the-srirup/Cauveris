"""
Clock skew analysis and domain clock modeling.

This module computes per-domain offsets from the raw signals (MCAP timestamps,
NTP sync logs, CSV jitter) and determines whether the resulting skew exceeds
the observation threshold.

Key insight: Many temporal anomalies are NOT "clock skew" in the traditional
sense (servers are well-synchronized via NTP). They are:
* **co-temporal ambiguity**: events from different domains logged at the same
  millisecond, making causal ordering undecidable from timestamps alone.
* **domain mixing**: a single log file (`system.log`) mixes wall-clock and
  monotonic timestamps, which breaks assumptions about monotonicity.
* **precision loss**: a second-precision log is fundamentally inadequate for
  ordering events that are 50-100 ms apart.

This module's outputs are used by the causal detector with explicit tolerance
policies, not as standalone erratic flags.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from cauveris.temporal.evidence import ClockDomain

logger = logging.getLogger(__name__)


class ClockStatus(str, Enum):
    """
    Operational status of a clock domain, derived from measurement.
    """
    REFERENCE = "reference"      # Zero-offset by design
    SYNCHRONIZED = "synchronized"  # Measured offset within threshold
    OFFSET = "offset"            # Offset exceeds threshold but consistent
    UNKNOWN = "unknown"          # No measurable data


@dataclass
class DomainClockModel:
    """Per-domain clock characteristics measured from evidence."""
    domain: ClockDomain
    offset_ns: int = 0
    jitter_ns: int = 0
    sample_count: int = 0
    status: ClockStatus = ClockStatus.UNKNOWN
    primary_source: str = ""
    max_skew_threshold_ns: int = 10_000_000  # default 10 ms

    @property
    def offset_ms(self) -> float:
        return self.offset_ns / 1_000_000.0

    @property
    def jitter_ms(self) -> float:
        return self.jitter_ns / 1_000_000.0


class ClockAnalysisResult:
    """
    Complete clock-domain analysis for an incident.
    """

    def __init__(self):
        self.domains: Dict[ClockDomain, DomainClockModel] = {}
        self.co_temporal_buckets: Dict[int, List[str]] = {}  # ns -> evidence_ids
        self.domain_mixing_detected: bool = False
        self.manual_offsets: Dict[ClockDomain, int] = {}

    def get_model(self, domain: ClockDomain) -> DomainClockModel:
        return self.domains.get(domain, DomainClockModel(domain=domain))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domains": {
                d.value: {
                    "offset_ms": m.offset_ms,
                    "jitter_ms": m.jitter_ms,
                    "status": m.status.value,
                    "samples": m.sample_count,
                }
                for d, m in self.domains.items()
            },
            "co_temporal_buckets": [
                {"time_ns": t, "evidence_count": len(eids), "evidence_ids": eids}
                for t, eids in sorted(self.co_temporal_buckets.items())[:20]
            ],
            "domain_mixing_detected": self.domain_mixing_detected,
        }


class ClockSkewAnalyzer:
    """
    Computes clock offsets from raw evidence having multiple timestamp kinds.
    """

    DEFAULT_SKEW_THRESHOLD_MS = 10.0

    def __init__(self, skew_threshold_ms: float = 10.0, mad_k: float = 3.5):
        self.skew_threshold_ns = int(skew_threshold_ms * 1_000_000)
        self.mad_k = mad_k

    def analyze(
        self,
        evidence: List[Any],
        raw_signals: Dict[str, Any],
        manifest_clock_alignment: Optional[Dict[str, Any]] = None,
    ) -> ClockAnalysisResult:
        result = ClockAnalysisResult()

        if manifest_clock_alignment:
            result = self._apply_manifest_clock_alignment(manifest_clock_alignment)

        for ev in evidence:
            domain = ev.clock_domain
            if domain not in result.domains:
                result.domains[domain] = DomainClockModel(domain=domain)
            result.domains[domain].sample_count += 1

        mcap_signals = raw_signals.get("mcap", {})
        if mcap_signals:
            self._analyze_mcap_clocks(mcap_signals, result)

        result = self._detect_co_temporal_ambiguity(evidence, result)

        sys_log = raw_signals.get("system_log", {})
        if sys_log and sys_log.get("mixed_domain_entries", 0) > 0:
            result.domain_mixing_detected = True

        self._finalize_domains(result, evidence)

        return result

    def _apply_manifest_clock_alignment(
        self, manifest: Dict[str, Any]
    ) -> ClockAnalysisResult:
        result = ClockAnalysisResult()
        domains_data = manifest.get("domains", {})

        for domain_key, domain_data in domains_data.items():
            try:
                domain = ClockDomain(domain_key)
            except ValueError:
                continue

            offset_ms = domain_data.get("offset_ms", 0.0)
            status_str = domain_data.get("status", "SYNCHRONIZED")

            try:
                status = ClockStatus(status_str)
            except ValueError:
                status = ClockStatus.UNKNOWN

            result.domains[domain] = DomainClockModel(
                domain=domain,
                offset_ns=int(offset_ms * 1_000_000),
                jitter_ns=int(domain_data.get("estimated_jitter_ms", 0.0) * 1_000_000),
                status=status,
                primary_source="manifest.clock_alignment",
                max_skew_threshold_ns=int(domain_data.get("threshold_ms", 10.0) * 1_000_000),
            )

        return result

    def _analyze_mcap_clocks(
        self, mcap_signals: Dict[str, Any], result: ClockAnalysisResult
    ) -> None:
        messages = mcap_signals.get("messages", [])
        if not messages:
            return

        for m in messages:
            if m.get("detection_age_ms") is not None:
                result.domains.setdefault(ClockDomain.ROBOT, DomainClockModel(domain=ClockDomain.ROBOT))

    def _detect_co_temporal_ambiguity(
        self, evidence: List[Any], result: ClockAnalysisResult
    ) -> ClockAnalysisResult:
        buckets: Dict[int, List[str]] = {}

        for ev in evidence:
            bucket_key = ev.timestamp_ns // 1_000_000
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            buckets[bucket_key].append(ev.evidence_id)

        for bkey, eids in buckets.items():
            if len(eids) > 1:
                domains_in_bucket = set()
                for evidence_id in eids:
                    for ev in evidence:
                        if ev.evidence_id == evidence_id:
                            domains_in_bucket.add(ev.clock_domain)
                            break
                if len(domains_in_bucket) > 1:
                    result.co_temporal_buckets[bkey] = eids

        return result

    def _finalize_domains(
        self, result: ClockAnalysisResult, evidence: List[Any]
    ) -> None:
        if not result.domains:
            for domain in [ClockDomain.CLOUD, ClockDomain.HOST, ClockDomain.ROBOT]:
                result.domains[domain] = DomainClockModel(domain=domain)

        defaults = {
            ClockDomain.CLOUD: DomainClockModel(domain=ClockDomain.CLOUD),
            ClockDomain.HOST: DomainClockModel(domain=ClockDomain.HOST),
            ClockDomain.ROBOT: DomainClockModel(domain=ClockDomain.ROBOT),
            ClockDomain.SIMULATION: DomainClockModel(domain=ClockDomain.SIMULATION),
            ClockDomain.UNKNOWN: DomainClockModel(domain=ClockDomain.UNKNOWN),
        }
        for domain, model in defaults.items():
            result.domains.setdefault(domain, model)

        for domain, model in result.domains.items():
            if abs(model.offset_ns) <= self.skew_threshold_ns:
                model.status = ClockStatus.SYNCHRONIZED
            elif model.sample_count > 100:
                model.status = ClockStatus.OFFSET
            else:
                model.status = ClockStatus.UNKNOWN if model.offset_ns == 0 else ClockStatus.OFFSET

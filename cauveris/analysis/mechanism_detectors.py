"""
Mechanism Detector Plugins for Cauveris.
Each detector implements:
- mechanism ID
- supporting evidence
- contradicting evidence
- missing evidence
- confidence
- repair preconditions
- simulation preconditions
- alternative hypotheses

Covers 8 canonical mechanisms:
1. Resource exhaustion (CPU/Memory/Disk)
2. Dependency timeout
3. Lock contention
4. Queue overflow or backpressure
5. Transport loss or jitter
6. Worker saturation
7. Clock skew
8. Arrival overload
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MechanismDetectionResult:
    mechanism_id: str
    confidence: float
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    repair_preconditions: List[str] = field(default_factory=list)
    simulation_preconditions: List[str] = field(default_factory=list)
    alternative_hypotheses: List[str] = field(default_factory=list)
    detected_parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MechanismDetector(ABC):
    """Abstract plugin for detecting failure mechanisms in arbitrary bundles."""

    @property
    @abstractmethod
    def mechanism_id(self) -> str:
        """Unique identifier of the mechanism."""
        pass

    @abstractmethod
    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        """Runs detection against evidence. Returns result if supported, else None."""
        pass


class ResourceExhaustionDetector(MechanismDetector):
    @property
    def mechanism_id(self) -> str:
        return "resource_exhaustion"

    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        supporting: List[str] = []
        contradicting: List[str] = []
        missing: List[str] = []

        oom_patterns = [
            r"oomkilled", r"out\s*of\s*memory", r"memoryerror", r"cgroup.*killed",
            r"cannot\s*allocate\s*memory", r"heap\s*exhaust", r"killed\s*process"
        ]
        matched_patterns = [p for p in oom_patterns if re.search(p, logs_text, re.IGNORECASE)]
        if matched_patterns:
            supporting.append(f"Logs indicate OOM/resource exhaustion: {matched_patterns[0]}")

        # Check metrics
        mem_val = metrics_dict.get("memory")
        mem_limit = config_entries.get("memory_limit_mb") or config_entries.get("memory")
        if mem_val and isinstance(mem_val, (int, float)) and mem_limit and isinstance(mem_limit, (int, float)):
            if mem_val >= mem_limit * 0.95:
                supporting.append(f"Memory usage ({mem_val}MB) reached or exceeded limit ({mem_limit}MB)")
            elif mem_val < mem_limit * 0.5:
                contradicting.append(f"Memory usage ({mem_val}MB) is well below configured limit ({mem_limit}MB)")
        elif not mem_val:
            missing.append("Peak memory telemetry (RSS/cgroup working set)")

        if not supporting:
            return None

        confidence = 0.90 if not contradicting else 0.40
        return MechanismDetectionResult(
            mechanism_id=self.mechanism_id,
            confidence=round(confidence, 3),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            repair_preconditions=["Configurable memory limit or batch size in configuration"],
            simulation_preconditions=["Memory footprint model calibrated against working set"],
            alternative_hypotheses=["worker_saturation", "arrival_overload"],
        )


class DependencyTimeoutDetector(MechanismDetector):
    @property
    def mechanism_id(self) -> str:
        return "dependency_timeout"

    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        supporting: List[str] = []
        contradicting: List[str] = []
        missing: List[str] = []

        timeout_patterns = [
            r"timed?\s*out", r"deadline\s*exceeded", r"context\s*deadline",
            r"etimedout", r"connection\s*timed?\s*out", r"upstream\s*timeout"
        ]
        matched = [p for p in timeout_patterns if re.search(p, logs_text, re.IGNORECASE)]
        if matched:
            supporting.append(f"Upstream dependency timed out: {matched[0]}")

        timeout_val = config_entries.get("timeout_ms") or config_entries.get("timeout")
        lat_val = metrics_dict.get("latency")
        if timeout_val and lat_val and isinstance(timeout_val, (int, float)) and isinstance(lat_val, (int, float)):
            if lat_val >= timeout_val:
                supporting.append(f"Latency ({lat_val}ms) breached timeout threshold ({timeout_val}ms)")
            else:
                contradicting.append(f"Latency ({lat_val}ms) did not breach timeout threshold ({timeout_val}ms)")
        else:
            missing.append("Upstream round-trip latency traces")

        if not supporting:
            return None

        confidence = 0.88 if not contradicting else 0.35
        return MechanismDetectionResult(
            mechanism_id=self.mechanism_id,
            confidence=round(confidence, 3),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            repair_preconditions=["Configurable client or RPC deadline in configuration"],
            simulation_preconditions=["Dependency response distribution and retry policy"],
            alternative_hypotheses=["transport_loss_jitter", "lock_contention"],
        )


class LockContentionDetector(MechanismDetector):
    @property
    def mechanism_id(self) -> str:
        return "lock_contention"

    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        supporting: List[str] = []
        contradicting: List[str] = []
        missing: List[str] = []

        lock_patterns = [
            r"deadlock", r"lock\s*timeout", r"lock\s*contention", r"mutex\s*contention",
            r"semaphore\s*timeout", r"unable\s*to\s*acquire\s*lock"
        ]
        matched = [p for p in lock_patterns if re.search(p, logs_text, re.IGNORECASE)]
        if matched:
            supporting.append(f"Lock contention signal in logs: {matched[0]}")

        lock_wait = metrics_dict.get("lock_wait")
        if lock_wait and isinstance(lock_wait, (int, float)):
            if lock_wait > 50:
                supporting.append(f"Elevated lock wait duration ({lock_wait}ms)")
            else:
                contradicting.append(f"Negligible lock wait duration recorded ({lock_wait}ms)")
        else:
            missing.append("Lock wait / blocked thread profiling metrics")

        if not supporting:
            return None

        confidence = 0.85 if not contradicting else 0.30
        return MechanismDetectionResult(
            mechanism_id=self.mechanism_id,
            confidence=round(confidence, 3),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            repair_preconditions=["Configurable lock timeout or concurrency limit"],
            simulation_preconditions=["Critical section duration and concurrency model"],
            alternative_hypotheses=["worker_saturation", "dependency_timeout"],
        )


class QueueOverflowDetector(MechanismDetector):
    @property
    def mechanism_id(self) -> str:
        return "queue_overflow_backpressure"

    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        supporting: List[str] = []
        contradicting: List[str] = []
        missing: List[str] = []

        q_patterns = [
            r"queue\s*full", r"queue\s*overflow", r"buffer\s*overflow", r"backpressure",
            r"rejectedexecutionexception", r"dropped\s*message", r"inbox\s*full"
        ]
        matched = [p for p in q_patterns if re.search(p, logs_text, re.IGNORECASE)]
        if matched:
            supporting.append(f"Queue/buffer full signal in logs: {matched[0]}")

        q_depth = metrics_dict.get("queue_depth")
        q_limit = config_entries.get("queue_depth") or config_entries.get("buffer_size")
        if q_depth and isinstance(q_depth, (int, float)) and q_limit and isinstance(q_limit, (int, float)):
            if q_depth >= q_limit:
                supporting.append(f"Queue depth ({q_depth}) reached buffer capacity ({q_limit})")
            elif q_depth < q_limit * 0.2:
                contradicting.append(f"Queue depth ({q_depth}) is comfortably below capacity ({q_limit})")
        elif not q_depth:
            missing.append("Queue depth / buffer fill telemetry")

        if not supporting:
            return None

        confidence = 0.87 if not contradicting else 0.35
        return MechanismDetectionResult(
            mechanism_id=self.mechanism_id,
            confidence=round(confidence, 3),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            repair_preconditions=["Configurable buffer size, queue limit or drop policy"],
            simulation_preconditions=["Arrival rate and worker drain rate model"],
            alternative_hypotheses=["arrival_overload", "worker_saturation"],
        )


class TransportLossJitterDetector(MechanismDetector):
    @property
    def mechanism_id(self) -> str:
        return "transport_loss_jitter"

    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        supporting: List[str] = []
        contradicting: List[str] = []
        missing: List[str] = []

        net_patterns = [
            r"packet\s*loss", r"retransmit", r"connection\s*reset", r"network\s*jitter",
            r"econnreset", r"transport\s*error", r"dropped\s*packets"
        ]
        matched = [p for p in net_patterns if re.search(p, logs_text, re.IGNORECASE)]
        if matched:
            supporting.append(f"Network transport anomalies in logs: {matched[0]}")

        loss_val = metrics_dict.get("loss")
        jitter_val = metrics_dict.get("jitter")
        if loss_val and isinstance(loss_val, (int, float)) and loss_val > 0.02:
            supporting.append(f"Elevated packet/sample loss rate ({loss_val * 100:.1f}%)")
        if jitter_val and isinstance(jitter_val, (int, float)) and jitter_val > 20:
            supporting.append(f"Elevated transport jitter ({jitter_val}ms)")

        if loss_val is not None and isinstance(loss_val, (int, float)) and loss_val == 0.0 and jitter_val == 0.0:
            contradicting.append("Zero network loss and jitter recorded in telemetry")

        if not loss_val and not jitter_val:
            missing.append("Network transport QoS metrics (loss, jitter, RTT)")

        if not supporting:
            return None

        confidence = 0.82 if not contradicting else 0.30
        return MechanismDetectionResult(
            mechanism_id=self.mechanism_id,
            confidence=round(confidence, 3),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            repair_preconditions=["Configurable retry policy, transport timeout or buffer"],
            simulation_preconditions=["Network link delay and loss distribution model"],
            alternative_hypotheses=["dependency_timeout", "clock_skew"],
        )


class WorkerSaturationDetector(MechanismDetector):
    @property
    def mechanism_id(self) -> str:
        return "worker_saturation"

    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        supporting: List[str] = []
        contradicting: List[str] = []
        missing: List[str] = []

        worker_patterns = [
            r"all\s*threads\s*busy", r"pool\s*exhausted", r"max_workers\s*reached",
            r"connection\s*pool\s*exhausted", r"worker\s*starvation"
        ]
        matched = [p for p in worker_patterns if re.search(p, logs_text, re.IGNORECASE)]
        if matched:
            supporting.append(f"Worker exhaustion patterns in logs: {matched[0]}")

        workers = config_entries.get("worker_count") or config_entries.get("workers")
        concurrency = metrics_dict.get("concurrency")
        if workers and concurrency and isinstance(workers, (int, float)) and isinstance(concurrency, (int, float)):
            if concurrency >= workers:
                supporting.append(f"Active concurrency ({concurrency}) saturated worker pool ({workers})")
            elif concurrency < workers * 0.3:
                contradicting.append(f"Active concurrency ({concurrency}) is far below pool capacity ({workers})")
        else:
            missing.append("Worker thread pool utilization metrics")

        if not supporting:
            return None

        confidence = 0.84 if not contradicting else 0.30
        return MechanismDetectionResult(
            mechanism_id=self.mechanism_id,
            confidence=round(confidence, 3),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            repair_preconditions=["Configurable worker pool count or concurrency limit"],
            simulation_preconditions=["Multi-server queueing model (M/M/c)"],
            alternative_hypotheses=["resource_exhaustion", "arrival_overload"],
        )


class ClockSkewDetector(MechanismDetector):
    @property
    def mechanism_id(self) -> str:
        return "clock_skew"

    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        supporting: List[str] = []
        contradicting: List[str] = []
        missing: List[str] = []

        clock_patterns = [
            r"clock\s*skew", r"time\s*drift", r"ntp\s*sync", r"timestamp\s*in\s*the\s*future",
            r"clock\s*unsynchronized", r"ptp\s*offset"
        ]
        matched = [p for p in clock_patterns if re.search(p, logs_text, re.IGNORECASE)]
        if matched:
            supporting.append(f"Time synchronization errors in logs: {matched[0]}")

        # Check negative latency or massive sudden forward jumps in logs
        if re.search(r"latency\s*:\s*-\d+", logs_text, re.IGNORECASE):
            supporting.append("Observed negative request latency indicative of unsynchronized clocks")

        if not supporting:
            return None

        confidence = 0.80 if not contradicting else 0.25
        return MechanismDetectionResult(
            mechanism_id=self.mechanism_id,
            confidence=round(confidence, 3),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            repair_preconditions=["Host NTP/PTP synchronization config or clock offset tolerance"],
            simulation_preconditions=["Dual-timebase alignment model"],
            alternative_hypotheses=["transport_loss_jitter"],
        )


class ArrivalOverloadDetector(MechanismDetector):
    @property
    def mechanism_id(self) -> str:
        return "arrival_overload"

    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        supporting: List[str] = []
        contradicting: List[str] = []
        missing: List[str] = []

        rate_val = metrics_dict.get("arrival_rate") or metrics_dict.get("throughput")
        svc_val = metrics_dict.get("service_time")
        workers = config_entries.get("worker_count") or 1

        # Check queue depth increase or batch wait backlog
        q_growth = [r"queue\s*depth\s*increasing", r"queue\s*rising", r"backlog\s*accumulating"]
        matched_q = [p for p in q_growth if re.search(p, logs_text, re.IGNORECASE)]
        if matched_q:
            supporting.append(f"Queue/backlog growth in logs: {matched_q[0]}")

        if rate_val and svc_val and isinstance(rate_val, (int, float)) and isinstance(svc_val, (int, float)) and svc_val > 0:
            capacity_hz = (1000.0 / svc_val) * float(workers)
            if rate_val > capacity_hz:
                supporting.append(f"Arrival rate ({rate_val:.1f}Hz) exceeds system capacity ({capacity_hz:.1f}Hz)")
            else:
                contradicting.append(f"Arrival rate ({rate_val:.1f}Hz) is within capacity ({capacity_hz:.1f}Hz)")
        else:
            overload_patterns = [r"rate\s*limit\s*exceeded", r"traffic\s*spike", r"too\s*many\s*requests", r"429\b"]
            matched = [p for p in overload_patterns if re.search(p, logs_text, re.IGNORECASE)]
            if matched:
                supporting.append(f"Traffic overload patterns in logs: {matched[0]}")

        if not rate_val:
            missing.append("Direct request arrival rate timeseries")

        if not supporting:
            return None

        confidence = 0.85 if not contradicting else 0.35
        return MechanismDetectionResult(
            mechanism_id=self.mechanism_id,
            confidence=round(confidence, 3),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            repair_preconditions=["Rate-limiter, ingress throttling or auto-scaler scaling factor"],
            simulation_preconditions=["G/G/c queueing model with burst distribution"],
            alternative_hypotheses=["queue_overflow_backpressure", "worker_saturation"],
        )


class ConnectionPoolExhaustionDetector(MechanismDetector):
    @property
    def mechanism_id(self) -> str:
        return "connection_pool_exhaustion"

    def detect(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> Optional[MechanismDetectionResult]:
        supporting: List[str] = []
        contradicting: List[str] = []
        missing: List[str] = []

        pool_patterns = [
            r"connection\s*pool\s*(?:exhausted|timeout|full|limit)",
            r"timeout:\s*pool\s*exhausted",
            r"too\s*many\s*connections",
            r"remaining\s*connection\s*slots",
            r"connection\s*(?:checkout|acquisition)\s*timeout",
            r"hikari.*(?:timeout|unavailable|is not available)",
            r"max_connections\s*exceeded",
            r"db\s*pool\s*(?:exhausted|full)",
            r"cannot\s*get\s*connection",
        ]
        matched = [p for p in pool_patterns if re.search(p, logs_text, re.IGNORECASE)]
        if matched:
            supporting.append(f"Connection pool exhaustion pattern: {matched[0]}")

        active_conn = metrics_dict.get("concurrency") or metrics_dict.get("active_connections")
        pool_size = None
        for k, v in config_entries.items():
            if any(term in k.lower() for term in ("pool_size", "max_connections", "max_pool", "max_active")):
                try:
                    pool_size = float(v)
                    break
                except (ValueError, TypeError):
                    pass

        if active_conn is not None and pool_size is not None:
            if float(active_conn) >= float(pool_size):
                supporting.append(f"Active connections ({active_conn}) >= pool limit ({pool_size})")
            else:
                contradicting.append(f"Active connections ({active_conn}) < pool limit ({pool_size})")

        if pool_size is None and not matched:
            return None

        if not supporting:
            return None

        confidence = 0.92 if not contradicting else 0.40
        return MechanismDetectionResult(
            mechanism_id=self.mechanism_id,
            confidence=round(confidence, 3),
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            missing_evidence=missing,
            repair_preconditions=["Configurable connection pool capacity (pool_size / max_connections)"],
            simulation_preconditions=["M/M/c/c finite-source connection acquisition queue model"],
            alternative_hypotheses=["dependency_timeout", "resource_exhaustion"],
            detected_parameters={"db_pool_size": pool_size} if pool_size else {},
        )


class MechanismDetectorRegistry:
    """Registry coordinating the mechanism detector plugins."""

    def __init__(self):
        self.detectors: List[MechanismDetector] = [
            ResourceExhaustionDetector(),
            DependencyTimeoutDetector(),
            LockContentionDetector(),
            QueueOverflowDetector(),
            TransportLossJitterDetector(),
            WorkerSaturationDetector(),
            ClockSkewDetector(),
            ArrivalOverloadDetector(),
            ConnectionPoolExhaustionDetector(),
        ]

    def detect_all(
        self,
        logs_text: str,
        metrics_dict: Dict[str, Any],
        config_entries: Dict[str, Any],
        bundle_path: Optional[Path] = None,
    ) -> List[MechanismDetectionResult]:
        results: List[MechanismDetectionResult] = []
        for det in self.detectors:
            try:
                res = det.detect(logs_text, metrics_dict, config_entries, bundle_path=bundle_path)
                if res is not None:
                    results.append(res)
            except Exception as e:
                logger.warning(f"Detector {det.mechanism_id} failed: {e}")

        # Sort highest confidence first
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

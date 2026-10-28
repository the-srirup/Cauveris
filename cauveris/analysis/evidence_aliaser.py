"""
Evidence Aliasing system for Cauveris.
Configurable alias dictionaries and matching rules for:
- latency, timeout, memory, CPU, queue depth, throughput,
- error count, loss, jitter, worker count, concurrency,
- lock wait, service time, arrival rate.

Retains original field name, canonical name, matching rule, confidence, and source.
Never silently converts unknown fields.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class EvidenceMatch:
    original_field: str
    canonical_name: str
    matching_rule: str  # e.g., "exact", "alias_lookup", "regex_pattern", "fuzzy_token"
    confidence: float
    source: str  # e.g., "metric", "log", "config", "trace"
    unit: Optional[str] = None
    value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Canonical signals with explicit synonyms, regex rules, and expected units
CANONICAL_SIGNALS: Dict[str, Dict[str, Any]] = {
    "latency": {
        "unit": "ms",
        "exact_aliases": [
            "latency", "latency_ms", "request_latency", "duration", "duration_ms",
            "resp_time", "response_time", "rtt", "rtt_ms", "delay", "delay_ms",
            "elapsed_ms", "elapsed_time", "age_ms", "e2e_latency"
        ],
        "regex_patterns": [
            r"latency(?:_ms)?$",
            r"response_time(?:_ms)?$",
            r"duration(?:_ms)?$",
            r"delay(?:_ms)?$",
        ],
    },
    "timeout": {
        "unit": "ms",
        "exact_aliases": [
            "timeout", "timeout_ms", "deadline", "deadline_ms", "request_timeout",
            "read_timeout", "connect_timeout", "client_timeout", "timeout_seconds",
            "max_wait_ms", "deadline_seconds"
        ],
        "regex_patterns": [
            r"timeout(?:_ms|_s|_seconds)?$",
            r"deadline(?:_ms|_s)?$",
        ],
    },
    "memory": {
        "unit": "mb",
        "exact_aliases": [
            "memory", "memory_mb", "mem_mb", "rss", "rss_mb", "ram_mb", "heap_mb",
            "memory_usage", "memory_limit", "mem_limit_mb", "heap_used", "resident_set_size",
            "working_set_mb", "cgroup_memory_mb"
        ],
        "regex_patterns": [
            r"(?:memory|mem|heap|ram)(?:_mb|_bytes|_limit|_usage)?$",
            r"rss(?:_mb)?$",
        ],
    },
    "cpu": {
        "unit": "percent",
        "exact_aliases": [
            "cpu", "cpu_percent", "cpu_usage", "cpu_utilization", "cpu_pct",
            "processor_pct", "cores_used", "cpu_load", "cpu_shares"
        ],
        "regex_patterns": [
            r"cpu(?:_percent|_pct|_utilization|_usage)?$",
        ],
    },
    "queue_depth": {
        "unit": "items",
        "exact_aliases": [
            "queue_depth", "queue_len", "backlog", "queue_size", "buffer_depth",
            "pending_requests", "in_flight_count", "unprocessed_items", "queue_length",
            "active_tasks", "queued_items"
        ],
        "regex_patterns": [
            r"queue(?:_depth|_len|_size|_length)?$",
            r"backlog(?:_size|_count)?$",
        ],
    },
    "throughput": {
        "unit": "req_per_s",
        "exact_aliases": [
            "throughput", "rps", "qps", "req_per_s", "requests_per_second",
            "frames_per_second", "fps", "items_per_second", "operations_per_sec",
            "txn_per_sec", "tps"
        ],
        "regex_patterns": [
            r"throughput$",
            r"(?:rps|qps|fps)$",
            r"req(?:uests)?_per_sec(?:ond)?$",
        ],
    },
    "error_count": {
        "unit": "count",
        "exact_aliases": [
            "error_count", "errors", "failed_requests", "failure_count",
            "error_total", "num_errors", "exceptions", "dropped_requests",
            "failed_count", "rejections"
        ],
        "regex_patterns": [
            r"error(?:s|_count|_total)?$",
            r"fail(?:ed|_count|_total)?$",
        ],
    },
    "loss": {
        "unit": "ratio",
        "exact_aliases": [
            "loss", "loss_rate", "packet_loss", "packet_loss_rate", "drop_rate",
            "dropped_ratio", "frame_loss_rate", "sample_drop_rate"
        ],
        "regex_patterns": [
            r"(?:packet_|frame_)?loss(?:_rate)?$",
            r"drop(?:ped)?_rate$",
        ],
    },
    "jitter": {
        "unit": "ms",
        "exact_aliases": [
            "jitter", "jitter_ms", "delay_jitter", "latency_jitter",
            "delay_variation", "rtt_jitter"
        ],
        "regex_patterns": [
            r"jitter(?:_ms)?$",
        ],
    },
    "worker_count": {
        "unit": "count",
        "exact_aliases": [
            "worker_count", "workers", "num_workers", "thread_pool_size",
            "threads", "pool_size", "server_workers", "worker_threads",
            "max_workers", "executor_threads"
        ],
        "regex_patterns": [
            r"(?:num_)?workers?$",
            r"(?:thread_)?pool_size$",
            r"max_workers$",
        ],
    },
    "concurrency": {
        "unit": "count",
        "exact_aliases": [
            "concurrency", "max_concurrency", "active_concurrency",
            "concurrent_requests", "parallelism", "simultaneous_requests"
        ],
        "regex_patterns": [
            r"concurrency$",
            r"parallelism$",
        ],
    },
    "lock_wait": {
        "unit": "ms",
        "exact_aliases": [
            "lock_wait", "lock_wait_ms", "contention_ms", "mutex_wait_ms",
            "lock_acquisition_time", "blocked_time_ms", "lock_duration_ms",
            "semaphore_wait_ms"
        ],
        "regex_patterns": [
            r"lock_wait(?:_ms)?$",
            r"contention(?:_ms)?$",
            r"mutex_wait(?:_ms)?$",
        ],
    },
    "service_time": {
        "unit": "ms",
        "exact_aliases": [
            "service_time", "service_time_ms", "processing_time", "processing_time_ms",
            "execution_time", "exec_time_ms", "inference_time", "compute_duration_ms"
        ],
        "regex_patterns": [
            r"service_time(?:_ms)?$",
            r"processing_time(?:_ms)?$",
            r"inference_time(?:_ms)?$",
        ],
    },
    "arrival_rate": {
        "unit": "items_per_s",
        "exact_aliases": [
            "arrival_rate", "arrival_rate_hz", "input_rate", "publish_rate",
            "ingress_rate", "ingress_rate_hz", "source_rate_hz", "inflow_rate", "rate_hz"
        ],
        "regex_patterns": [
            r"arrival_rate(?:_hz)?$",
            r"ingress_rate(?:_hz)?$",
            r"input_rate(?:_hz)?$",
        ],
    },
}


class EvidenceAliaser:
    """Matches arbitrary field and metric names against canonical signals transparently."""

    def __init__(self, custom_signals: Optional[Dict[str, Dict[str, Any]]] = None):
        self.signals = dict(CANONICAL_SIGNALS)
        if custom_signals:
            for k, v in custom_signals.items():
                if k in self.signals:
                    self.signals[k].update(v)
                else:
                    self.signals[k] = v

    def match(
        self,
        raw_field_name: str,
        source: str = "metric",
        value: Optional[Any] = None,
    ) -> Optional[EvidenceMatch]:
        """
        Attempts to match a raw field name to a canonical signal.
        Returns EvidenceMatch if matched, or None if unknown.
        Does not silently convert unknown fields.
        """
        if not raw_field_name or not isinstance(raw_field_name, str):
            return None

        # Clean string
        normalized = raw_field_name.strip().lower()
        last_component = normalized.split(".")[-1].split("/")[-1].split(":")[-1]

        # 1. Exact canonical name match
        if last_component in self.signals:
            spec = self.signals[last_component]
            return EvidenceMatch(
                original_field=raw_field_name,
                canonical_name=last_component,
                matching_rule="exact",
                confidence=1.0,
                source=source,
                unit=spec.get("unit"),
                value=value,
            )

        # 2. Exact alias lookup
        for canon, spec in self.signals.items():
            exacts = [alias.lower() for alias in spec.get("exact_aliases", [])]
            if last_component in exacts or normalized in exacts:
                return EvidenceMatch(
                    original_field=raw_field_name,
                    canonical_name=canon,
                    matching_rule="alias_lookup",
                    confidence=0.95,
                    source=source,
                    unit=spec.get("unit"),
                    value=value,
                )

        # 3. Regex pattern match
        for canon, spec in self.signals.items():
            for pat in spec.get("regex_patterns", []):
                if re.search(pat, last_component, re.IGNORECASE) or re.search(pat, normalized, re.IGNORECASE):
                    return EvidenceMatch(
                        original_field=raw_field_name,
                        canonical_name=canon,
                        matching_rule="regex_pattern",
                        confidence=0.85,
                        source=source,
                        unit=spec.get("unit"),
                        value=value,
                    )

        # 4. Fuzzy token matching for compound keys (e.g., "camera_frame_latency_measured")
        tokens = set(re.split(r"[_\-./\s:]+", normalized))
        for canon, spec in self.signals.items():
            canon_tokens = set(re.split(r"[_\-./\s:]+", canon))
            if canon_tokens.issubset(tokens):
                return EvidenceMatch(
                    original_field=raw_field_name,
                    canonical_name=canon,
                    matching_rule="fuzzy_token",
                    confidence=0.75,
                    source=source,
                    unit=spec.get("unit"),
                    value=value,
                )

        # Unknown field - never silently convert
        return None

    def match_dictionary(
        self,
        raw_dict: Dict[str, Any],
        source: str = "metric",
    ) -> Tuple[Dict[str, EvidenceMatch], Dict[str, Any]]:
        """
        Processes a dictionary of raw fields.
        Returns:
            (matched_evidence, unknown_fields)
        """
        matched: Dict[str, EvidenceMatch] = {}
        unknown: Dict[str, Any] = {}

        for k, v in raw_dict.items():
            m = self.match(k, source=source, value=v)
            if m is not None:
                matched[m.canonical_name] = m
            else:
                unknown[k] = v

        return matched, unknown

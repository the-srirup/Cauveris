"""
Temporal evidence model and extraction.

This module bridges two worlds:

* ``extract_from_timeline`` consumes the *already-built* timeline events from
  ``TimelineBuilder`` — these are convenient because they already carry
  ``relative_timestamp_ns`` and a ``lane`` tag, but they have sugar-coated away
  the raw clock signals (MCAP triple-clock, JSONL line order vs wall clock,
  ``system.log`` NTP + monotonic bracketing, duplicate CSV columns).

* ``extract_raw_signals`` re-reads the *raw bundle files* to recover those
  signals. The analyzer uses both sources: the timeline for scale and the raw
  signals for the precise anomaly criteria.
"""
from __future__ import annotations

import csv
import json
import logging
import re
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Enums / small types
# ----------------------------------------------------------------------
class ClockDomain(str, Enum):
    """Logical clock domains present in the evidence."""
    CLOUD = "cloud"           # OTel traces, cloud-service.jsonl, cloud metrics
    HOST = "host"             # deployment events, system.log (mixed)
    ROBOT = "robot"           # ros-nodes.jsonl, MCAP topics
    SIMULATION = "simulation" # MCAP simulation clock (if present)
    UNKNOWN = "unknown"


class TimestampKind(str, Enum):
    """
    Kind of timestamp, which determines its precision and semantics.

    The kind controls how much *precision loss* the analyzer tolerates before
    treating an out-of-order pair as a potential inversion.
    """
    NANOSECOND_WALL = "nanosecond_wall"        # OTel spans, MCAP log_time
    NANOSECOND_MONOTONIC = "nanosecond_monotonic"  # kernel uptime bracket
    MICROSECOND_WALL = "microsecond_wall"      # JSONL ISO8601 with µs
    SECOND_WALL = "second_wall"                # system.log ISO8601 to-the-second
    RELATIVE = "relative"                      # relative_s / relative_ns from builder
    UNKNOWN = "unknown"


class CausalityProvenance(str, Enum):
    """
    How the analyzer learned a cause->effect edge exists.

    Used by ``TolerancePolicy`` to set per-edge tolerance.
    """
    OTEL_TRACE_ORDER = "otel_trace_order"
    ROS_TOPIC_ORDER = "ros_topic_order"
    LOG_NODE_ORDER = "log_node_order"
    CROSS_DOMAIN_HANDOFF = "cross_domain_handoff"
    DEPLOYMENT_CHAIN = "deployment_chain"
    TEMPORAL_PROXIMITY = "temporal_proximity"


# ----------------------------------------------------------------------
# Evidence record
# ----------------------------------------------------------------------
@dataclass(slots=True)
class TemporalEvidence:
    """
    A single event with its fully qualified temporal fingerprint.
    """
    # Synthesized deterministic ID
    evidence_id: str

    # Original fields
    timestamp_ns: int                # absolute wall-clock nanoseconds (best effort)
    timestamp_kind: TimestampKind    # precision class
    lane: str                        # logical lane (builder's lane)
    source: str                      # file path relative to bundle
    message: str                     # human readable summary

    # Domain & breadcrumb
    clock_domain: ClockDomain
    source_type: str                 # builder's source_type

    # Causal hints (may be empty)
    parent_candidates: List[str] = field(default_factory=list)
    child_candidates: List[str] = field(default_factory=list)

    # Provenance tags for *why* the analyzer might believe these edges
    parent_provenance: Dict[str, CausalityProvenance] = field(default_factory=dict)
    child_provenance: Dict[str, CausalityProvenance] = field(default_factory=dict)

    # Raw-signal extras (filled by RawSignalExtractor)
    # For MCAP: header_stamp_ns, publish_time_ns
    extra: Dict[str, Any] = field(default_factory=dict)

    # ----------------------------------------------------------------
    @property
    def precision_ns(self) -> int:
        """Estimated timestamp precision in nanoseconds."""
        mapping = {
            TimestampKind.NANOSECOND_WALL: 1,
            TimestampKind.NANOSECOND_MONOTONIC: 1,
            TimestampKind.MICROSECOND_WALL: 1_000,
            TimestampKind.SECOND_WALL: 1_000_000_000,
            TimestampKind.RELATIVE: 1,
            TimestampKind.UNKNOWN: 1_000_000_000,
        }
        return mapping.get(self.timestamp_kind, 1_000_000_000)


# ----------------------------------------------------------------------
# Helpers for deterministic IDs
# ----------------------------------------------------------------------
def _domain_from_source_type(source_type: str) -> ClockDomain:
    mapping = {
        "otel_trace": ClockDomain.CLOUD,
        "csv_metrics": ClockDomain.CLOUD,
        "deployment_json": ClockDomain.HOST,
        "operator_note": ClockDomain.HOST,
        "jsonl_log": ClockDomain.ROBOT,
        "text_log": ClockDomain.HOST,  # system.log is mixed, caller can refine
        "mcap_recording": ClockDomain.ROBOT,
    }
    return mapping.get(source_type, ClockDomain.UNKNOWN)


def _kind_from_source_type(source_type: str, original_ts: str) -> TimestampKind:
    if source_type in {"otel_trace", "mcap_recording"}:
        return TimestampKind.NANOSECOND_WALL
    if source_type == "jsonl_log" and "." in original_ts and "Z" in original_ts:
        return TimestampKind.MICROSECOND_WALL
    if source_type == "text_log" and "T" in original_ts:
        # system.log uses second precision (no fractional)
        return TimestampKind.SECOND_WALL
    if source_type == "csv_metrics":
        return TimestampKind.MICROSECOND_WALL
    if source_type == "deployment_json":
        return TimestampKind.MICROSECOND_WALL
    if source_type == "operator_note":
        return TimestampKind.SECOND_WALL
    return TimestampKind.UNKNOWN


def _synth_evidence_id(source_type: str, source: str, seq: int) -> str:
    """Deterministic ID: source_type + file + sequence."""
    key = f"{source_type}:{source}#{seq:06d}"
    # Short stable hash to keep IDs readable-ish in logs
    short = hashlib.md5(key.encode()).hexdigest()[:8]
    return f"{source_type}:{source}#{seq:06d}.{short}"


# ----------------------------------------------------------------------
# Timeline → Evidence extraction
# ----------------------------------------------------------------------
def extract_from_timeline(
    timeline_events: List[Dict[str, Any]],
    bundle_path: Optional[Path] = None,
) -> List[TemporalEvidence]:
    """
    Convert the builder's timeline events into ``TemporalEvidence`` objects.

    The timeline events are already sorted by ``timestamp_ns`` and carry
    ``relative_timestamp_ns``. We re-attribute a deterministic ``evidence_id``
    and enrich each with its clock domain / timestamp kind / provenance hints.
    """
    evidence: List[TemporalEvidence] = []

    # Group by (source_type, source) to assign sequence numbers
    groups: Dict[Tuple[str, str], int] = defaultdict(int)

    for event in timeline_events:
        source_type = event.get("source_type", "unknown")
        source = event.get("source", "unknown")
        seq = groups[(source_type, source)]
        groups[(source_type, source)] = seq + 1

        evidence_id = _synth_evidence_id(source_type, source, seq)

        # Clock domain
        domain = _domain_from_source_type(source_type)

        # Timestamp kind
        ts_kind = _kind_from_source_type(source_type, event.get("original_timestamp", ""))

        # Lane-to-handoff heuristic for parent candidates
        parent_candidates: List[str] = []
        child_candidates: List[str] = []
        parent_prov: Dict[str, CausalityProvenance] = {}
        child_prov: Dict[str, CausalityProvenance] = {}

        te = TemporalEvidence(
            evidence_id=evidence_id,
            timestamp_ns=event.get("timestamp_ns", 0),
            timestamp_kind=ts_kind,
            lane=event.get("lane", "unknown"),
            source=source,
            message=event.get("message", ""),
            clock_domain=domain,
            source_type=source_type,
            parent_candidates=parent_candidates,
            child_candidates=child_candidates,
            parent_provenance=parent_prov,
            child_provenance=child_prov,
            extra={
                "original_timestamp": event.get("original_timestamp"),
                "attributes": event.get("attributes", {}),
                "confidence": event.get("confidence", 0.0),
                "status": event.get("status", ""),
            },
        )
        evidence.append(te)

    # Second pass: add parent/child hints based on seminaric lane/topic rules
    _add_timeline_causal_hints(evidence, bundle_path)

    return evidence


def _add_timeline_causal_hints(
    evidence: List[TemporalEvidence],
    bundle_path: Optional[Path],
) -> None:
    """
    Add parent/child candidate links using *semantic* rules encoded from system
    knowledge (not from pre-declared dependencies, which do not exist).

    Rules:
    1. OTel spans in the *same trace* are ordered by start time → OTEL_TRACE_ORDER
    2. MCAP topic ordering: /detections → /tf → /cmd_vel → /safety_status
       → ROS_TOPIC_ORDER
    3. ROS log node pipeline: detection_listener → navigation_controller → safety_monitor
       → LOG_NODE_ORDER
    4. Deployment v42 at 08:00:00Z → any event after it → DEPLOYMENT_CHAIN
    5. Within-lane temporal proximity → TEMPORAL_PROXIMITY
    6. Cross-lane temporal proximity at handoff boundaries → CROSS_DOMAIN_HANDOFF
    """
    # 1. OTel trace order
    traces_by_trace_id: Dict[str, List[TemporalEvidence]] = defaultdict(list)
    for ev in evidence:
        if ev.source_type == "otel_trace":
            trace_id = ev.extra.get("attributes", {}).get("trace_id", "")
            if trace_id:
                traces_by_trace_id[trace_id].append(ev)
    for trace_events in traces_by_trace_id.values():
        trace_events.sort(key=lambda e: e.timestamp_ns)
        for i in range(len(trace_events) - 1):
            a, b = trace_events[i], trace_events[i + 1]
            a.child_candidates.append(b.evidence_id)
            a.child_provenance[b.evidence_id] = CausalityProvenance.OTEL_TRACE_ORDER
            b.parent_candidates.append(a.evidence_id)
            b.parent_provenance[a.evidence_id] = CausalityProvenance.OTEL_TRACE_ORDER

    # 2. MCAP topic pipeline
    mcap_by_topic: Dict[str, List[TemporalEvidence]] = defaultdict(list)
    for ev in evidence:
        if ev.source_type == "mcap_recording":
            topic = ev.extra.get("attributes", {}).get("topic", "")
            if topic:
                mcap_by_topic[topic].append(ev)
    topic_pipeline = ["/detections", "/tf", "/cmd_vel", "/safety_status"]
    topic_index = {t: i for i, t in enumerate(topic_pipeline)}
    sorted_topics = sorted(
        [(topic_index.get(t, 999), t, evs) for t, evs in mcap_by_topic.items() if t in topic_index],
        key=lambda x: x[0],
    )
    for _, t, evs in sorted_topics:
        evs.sort(key=lambda e: e.timestamp_ns)
        if len(evs) > 1:
            for i in range(len(evs) - 1):
                a, b = evs[i], evs[i + 1]
                a.child_candidates.append(b.evidence_id)
                a.child_provenance[b.evidence_id] = CausalityProvenance.ROS_TOPIC_ORDER
                b.parent_candidates.append(a.evidence_id)
                b.parent_provenance[a.evidence_id] = CausalityProvenance.ROS_TOPIC_ORDER
        # Cross-topic edges: last event of topic -> first event of next topic
    for i in range(len(sorted_topics) - 1):
        _, _, cur_evs = sorted_topics[i]
        _, _, next_evs = sorted_topics[i + 1]
        if cur_evs and next_evs:
            a = cur_evs[-1]
            b = next_evs[0]
            a.child_candidates.append(b.evidence_id)
            a.child_provenance[b.evidence_id] = CausalityProvenance.CROSS_DOMAIN_HANDOFF
            b.parent_candidates.append(a.evidence_id)
            b.parent_provenance[a.evidence_id] = CausalityProvenance.CROSS_DOMAIN_HANDOFF

    # 3. ROS log node pipeline
    ros_nodes = [e for e in evidence if e.source_type == "jsonl_log"]
    node_order = ["detection_listener", "navigation_controller", "safety_monitor"]
    node_index = {n: i for i, n in enumerate(node_order)}
    ros_nodes.sort(key=lambda e: e.timestamp_ns)
    for i in range(len(ros_nodes) - 1):
        a, b = ros_nodes[i], ros_nodes[i + 1]
        a_node = a.extra.get("attributes", {}).get("node", "")
        b_node = b.extra.get("attributes", {})
        b_node_name = b_node.get("node", "")
        if a_node in node_index and b_node_name in node_index and node_index[a_node] < node_index[b_node_name]:
            a.child_candidates.append(b.evidence_id)
            a.child_provenance[b.evidence_id] = CausalityProvenance.LOG_NODE_ORDER
            b.parent_candidates.append(a.evidence_id)
            b.parent_provenance[a.evidence_id] = CausalityProvenance.LOG_NODE_ORDER

    # 4. Deployment chain
    deployment_events = [e for e in evidence if e.source_type == "deployment_json"]
    for dep in deployment_events:
        for ev in evidence:
            if ev is dep or ev.timestamp_ns <= dep.timestamp_ns:
                continue
            # Only link to the deployment that is closest in configuration space
            # (here, we just link to all later events; tolerance will gate)
            dep.child_candidates.append(ev.evidence_id)
            dep.child_provenance[ev.evidence_id] = CausalityProvenance.DEPLOYMENT_CHAIN
            ev.parent_candidates.append(dep.evidence_id)
            ev.parent_provenance[dep.evidence_id] = CausalityProvenance.DEPLOYMENT_CHAIN

    # 5. Within-lane proximity
    by_lane: Dict[str, List[TemporalEvidence]] = defaultdict(list)
    for ev in evidence:
        by_lane[ev.lane].append(ev)
    for lane_evs in by_lane.values():
        lane_evs.sort(key=lambda e: e.timestamp_ns)
        for i in range(len(lane_evs) - 1):
            a, b = lane_evs[i], lane_evs[i + 1]
            if (b.timestamp_ns - a.timestamp_ns) <= 250_000_000:  # 250 ms
                a.child_candidates.append(b.evidence_id)
                a.child_provenance[b.evidence_id] = CausalityProvenance.TEMPORAL_PROXIMITY
                b.parent_candidates.append(a.evidence_id)
                b.parent_provenance[a.evidence_id] = CausalityProvenance.TEMPORAL_PROXIMITY

    # 6. Cross-lane handoff proximity
    handoff_lanes = [
        ("cloud_requests", "detection_publication"),
        ("detection_publication", "tf_events"),
        ("tf_events", "controller_latency"),
        ("controller_latency", "safety_state"),
    ]
    for from_lane, to_lane in handoff_lanes:
        from_evs = by_lane.get(from_lane, [])
        to_evs = by_lane.get(to_lane, [])
        if not from_evs or not to_evs:
            continue
        # Link each from_event to the first to_event after it within window
        for a in from_evs:
            for b in to_evs:
                if b.timestamp_ns > a.timestamp_ns and (b.timestamp_ns - a.timestamp_ns) <= 500_000_000:
                    a.child_candidates.append(b.evidence_id)
                    a.child_provenance[b.evidence_id] = CausalityProvenance.CROSS_DOMAIN_HANDOFF
                    b.parent_candidates.append(a.evidence_id)
                    b.parent_provenance[a.evidence_id] = CausalityProvenance.CROSS_DOMAIN_HANDOFF
                    break


# ----------------------------------------------------------------------
# Raw signal extraction (bundle-level)
# ----------------------------------------------------------------------
class RawSignalExtractor:
    """
    Reads the raw bundle files to recover signals lost in the timeline projection.
    """

    def __init__(self, bundle_path: Path):
        self.bundle_path = Path(bundle_path)
        self.signals: Dict[str, Any] = {}

    def extract_all(self) -> Dict[str, Any]:
        """Run all extractors and return a signal bag."""
        self.signals = {
            "mcap": self.extract_mcap_signals(),
            "system_log": self.extract_system_log_signals(),
            "csv_metrics": self.extract_csv_signals(),
            "jsonl_order": self.extract_jsonl_order_signals(),
        }
        return self.signals

    # ------------------------------------------------------------------ #
    # MCAP triple-clock: log_time, publish_time, embedded header.stamp_ns
    # ------------------------------------------------------------------ #
    def extract_mcap_signals(self) -> Dict[str, Any]:
        """
        Return per-message dict with keys:
          - topic
          - log_time_ns
          - publish_time_ns
          - header_stamp_ns (if present)
          - detection_age_ms (computed as log_time - header_stamp when available)
        """
        try:
            from mcap.reader import make_reader
        except Exception:
            return {}

        messages = []
        with open(self.bundle_path / "recordings" / "robot_run.mcap", "rb") as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages():
                try:
                    payload = json.loads(message.data.decode("utf-8"))
                except Exception:
                    payload = {}

                header_stamp = None
                if isinstance(payload, dict):
                    header = payload.get("header", {})
                    if isinstance(header, dict):
                        stamp = header.get("stamp_ns")
                        if isinstance(stamp, (int, float)):
                            header_stamp = int(stamp)

                age_ms = None
                if header_stamp is not None:
                    age_ms = (message.log_time - header_stamp) / 1_000_000.0

                messages.append({
                    "topic": channel.topic,
                    "log_time_ns": message.log_time,
                    "publish_time_ns": message.publish_time,
                    "header_stamp_ns": header_stamp,
                    "detection_age_ms": age_ms,
                    "payload_keys": list(payload.keys()) if isinstance(payload, dict) else [],
                })

        # Co-temporal ambiguities: messages on different topics sharing log_time
        by_log_time: Dict[int, List[Dict]] = defaultdict(list)
        for m in messages:
            by_log_time[m["log_time_ns"]].append(m)
        ambiguities = {
            t: msgs for t, msgs in by_log_time.items() if len(msgs) > 1
        }

        # Back-to-back detection: /cmd_vel (estop) and /safety_status at identical time
        estop_and_safety = []
        for t, msgs in ambiguities.items():
            topics = {m["topic"] for m in msgs}
            if "/cmd_vel" in topics and "/safety_status" in topics:
                estop_and_safety.append({"time_ns": t, "topics": list(topics)})

        return {
            "messages": messages,
            "co_temporal_ambiguities": ambiguities,
            "estop_safety_co_temporal": estop_and_safety,
        }

    # ------------------------------------------------------------------ #
    # system.log: NTP offset + monotonic bracketing + second precision
    # ------------------------------------------------------------------ #
    def extract_system_log_signals(self) -> Dict[str, Any]:
        path = self.bundle_path / "logs" / "system.log"
        if not path.exists():
            return {}

        content = path.read_text(encoding="utf-8", errors="ignore")
        monotonic_brackets: List[Tuple[int, float]] = []
        signals: Dict[str, Any] = {
            "ntp_offset_sec": None,
            "monotonic_brackets": monotonic_brackets,
            "second_precision_samples": 0,
            "mixed_domain_entries": 0,
        }

        # NTP offset
        m = re.search(r"offset\s+([+-]?\d+\.?\d*)s", content)
        if m:
            signals["ntp_offset_sec"] = float(m.group(1))

        # Monotonic kernel bracket [10421.11]
        for line in content.splitlines():
            m2 = re.search(r"\[(\d+\.\d+)\]", line)
            if m2:
                mono_sec = float(m2.group(1))
                # Find wall timestamp on same line
                ts_match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)", line)
                if ts_match:
                    dt = datetime.fromisoformat(ts_match.group(1).replace("Z", "+00:00"))
                    wall_ns = int(dt.timestamp() * 1_000_000_000)
                    signals["monotonic_brackets"].append((wall_ns, mono_sec))
                    signals["second_precision_samples"] += 1
                else:
                    signals["mixed_domain_entries"] += 1

        return signals

    # ------------------------------------------------------------------ #
    # CSV duplicate columns / precision
    # ------------------------------------------------------------------ #
    def extract_csv_signals(self) -> Dict[str, Any]:
        metrics_dir = self.bundle_path / "metrics"
        if not metrics_dir.exists():
            return {}

        duplicate_columns: List[Dict[str, Any]] = []
        signals: Dict[str, Any] = {
            "duplicate_columns": duplicate_columns,
            "column_precision": {}
        }

        for csv_path in metrics_dir.glob("*.csv"):
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    if not header:
                        continue
                    seen: Dict[str, List[int]] = {}
                    for idx, col in enumerate(header):
                        seen.setdefault(col.lower(), []).append(idx)
                    dupes = [col for col, idxs in seen.items() if len(idxs) > 1]
                    if dupes:
                        signals["duplicate_columns"].append({
                            "file": str(csv_path.relative_to(self.bundle_path)),
                            "duplicates": dupes,
                        })

                    # Precision check: fractional seconds in timestamp column
                    ts_col = next((c for c in header if "time" in c.lower()), header[0])
                    ts_col_idx = header.index(ts_col)
                    frac_samples = 0
                    non_frac = 0
                    f.seek(0)
                    next(reader, None)
                    for row in reader:
                        if not row or ts_col_idx >= len(row):
                            continue
                        ts_str = row[ts_col_idx]
                        if "." in ts_str:
                            frac_samples += 1
                        else:
                            non_frac += 1
                    signals["column_precision"][str(csv_path.relative_to(self.bundle_path))] = {
                        "timestamp_column": ts_col,
                        "microsecond_samples": frac_samples,
                        "second_only_samples": non_frac,
                    }
            except Exception as exc:
                logger.debug("CSV signal extraction failed for %s: %s", csv_path, exc)

        return signals

    # ------------------------------------------------------------------ #
    # JSONL line number vs wall-clock order
    # ----------------------------------------------------------------------
    def extract_jsonl_order_signals(self) -> Dict[str, Any]:
        logs_dir = self.bundle_path / "logs"
        if not logs_dir.exists():
            return {}

        signals: Dict[str, Any] = {"files": {}}

        for jsonl_path in logs_dir.glob("*.jsonl"):
            detail: List[Dict[str, Any]] = []
            file_signals: Dict[str, Any] = {
                "line_count": 0,
                "inversions": 0,
                "detail": detail,
            }
            prev_ts = None
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    file_signals["line_count"] += 1
                    try:
                        entry = json.loads(line)
                        ts_str = entry.get("timestamp", "")
                        if ts_str:
                            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            ts_ns = int(dt.timestamp() * 1_000_000_000)
                            if prev_ts is not None and ts_ns < prev_ts:
                                file_signals["inversions"] += 1
                                file_signals["detail"].append({
                                    "line": line_num,
                                    "prev_ns": prev_ts,
                                    "curr_ns": ts_ns,
                                    "delta_ns": ts_ns - prev_ts,
                                })
                            prev_ts = ts_ns
                    except Exception:
                        pass
            signals["files"][str(jsonl_path.relative_to(self.bundle_path))] = file_signals

        return signals

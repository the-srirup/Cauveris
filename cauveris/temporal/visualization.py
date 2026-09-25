"""
Visualization data generation for temporal anomalies.

Returns data structures suitable for rendering an interactive timeline
that highlights causality violations, time loops, and co-temporal ambiguities.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def build_timeline_visualization_data(
    temporal_result: Dict[str, Any],
    original_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a visualization-ready payload from temporal analysis results.

    Args:
        temporal_result: Output of ``TemporalAnalyzer.analyze_incident``
        original_events: The incident's timeline events

    Returns:
        Dict with ``events``, ``connections``, ``anomalies``, ``loops`` keys
        suitable for plotting in a D3-style web timeline.
    """
    events = []
    connections = []
    anomaly_points = []

    # Index events by ID for quick lookup
    event_by_id = {}
    for evt in original_events:
        evt_id = evt.get("event_id") or evt.get("evidence_id", "")
        event_by_id[evt_id] = evt
        events.append({
            "id": evt_id,
            "ts": evt.get("relative_timestamp_s") or (evt.get("timestamp_ns", 0) / 1e9),
            "domain": _domain_from_event(evt),
            "label": _short_label(evt),
            "merge_group": _merge_group(evt),
            "confidence": evt.get("temporal_trust", 1.0),
        })

    # Build causal connections (cause -> effect)
    for ev in original_events:
        src = ev.get("event_id") or ev.get("evidence_id", "")
        for child in ev.get("child_candidates", []):
            connections.append({
                "source": src,
                "target": child,
                "provenance": ev.get("child_provenance", {}).get(child, "unknown"),
                "type": "causal_edge",
            })

    # Append causality violations as marked edges
    for violation in temporal_result.get("causality_violations", []):
        a = violation.get("event_a", "")
        b = violation.get("event_b", "")
        connections.append({
            "source": a,
            "target": b,
            "type": "violation",
            "confidence": violation.get("confidence", 0),
            "description": violation.get("description", ""),
        })

    # Anomalies as anomaly markers
    for anom in temporal_result.get("temporal_anomalies", []):
        for eid in anom.get("affected_events", []):
            anomaly_points.append({
                "id": eid,
                "type": anom.get("type", "unknown"),
                "severity": anom.get("severity", 0.5),
                "confidence": anom.get("confidence", 0.5),
                "explanation": anom.get("explanation", ""),
            })

    # Time loops
    for loop in temporal_result.get("time_loops", []):
        loop_events = loop.get("events", [])
        for i in range(len(loop_events)):
            src = loop_events[i]
            tgt = loop_events[(i + 1) % len(loop_events)]
            connections.append({
                "source": src,
                "target": tgt,
                "type": "loop_edge",
                "loop_id": loop.get("loop_id"),
                "confidence": loop.get("confidence", 0.5),
            })

    # Untrusted windows as timeline bands
    untrusted_bands = []
    for win in temporal_result.get("untrusted_windows", []):
        untrusted_bands.append({
            "start_s": win.get("start_s", 0),
            "end_s": win.get("end_s", 0),
            "reason": win.get("type", "unknown"),
            "description": win.get("description", ""),
        })

    return {
        "events": events,
        "connections": connections,
        "anomaly_points": anomaly_points,
        "untrusted_bands": untrusted_bands,
        "summary": {
            "total_events": len(events),
            "connections": len(connections),
            "anomaly_count": len(anomaly_points),
            "time_loop_count": sum(1 for c in connections if c.get("type") == "loop_edge"),
            "is_anomalous": temporal_result.get("is_time_anomalous", False),
            "confidence": temporal_result.get("temporal_confidence_score", 1.0),
        },
    }


def _domain_from_event(evt: Dict[str, Any]) -> str:
    """Extract a short domain label from an event dict."""
    source_type = evt.get("source_type", "")
    lane = evt.get("lane", "")
    if source_type == "otel_trace":
        return "cloud"
    if source_type in ("jsonl_log", "text_log"):
        if "ros" in source_type.lower() or "detection" in lane:
            return "robot"
        return "host"
    if source_type == "mcap_recording":
        return "robot"
    if source_type == "csv_metrics":
        return "cloud"
    if source_type == "deployment_json":
        return "host"
    if source_type == "operator_note":
        return "human"
    return "unknown"


def _short_label(evt: Dict[str, Any]) -> str:
    """Get a short label for an event."""
    msg = evt.get("message", "")
    if len(msg) > 60:
        return msg[:57] + "..."
    return msg


def _merge_group(evt: Dict[str, Any]) -> Optional[str]:
    """Get a group key for events that should be rendered together."""
    source = evt.get("source", "")
    ts_ns = evt.get("timestamp_ns", 0)
    # Group by source file and millisecond
    return f"{source}@{ts_ns // 1_000_000}"

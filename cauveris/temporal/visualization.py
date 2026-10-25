"""
Visualization data generation for temporal anomalies.

Returns data structures suitable for rendering an interactive timeline
that highlights causality violations, time loops, and co-temporal ambiguities.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def build_timeline_visualization_data(
    temporal_result: Dict[str, Any],
    original_events: List[Dict[str, Any]],
    bundle_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Build a visualization-ready payload from temporal analysis results.

    Args:
        temporal_result: Output of ``TemporalAnalyzer.analyze_incident``
        original_events: The incident's timeline events
        bundle_path: Optional bundle path, used to re-derive the evidence
            graph when the temporal result does not carry one (e.g. when it
            was restored from a report written before the graph existed).

    Returns:
        Dict with ``events``, ``connections``, ``anomaly_points``,
        ``untrusted_bands`` and ``summary`` keys suitable for plotting in a
        D3-style web timeline.
    """
    events: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []
    anomaly_points: List[Dict[str, Any]] = []

    graph = _resolve_evidence_graph(temporal_result, original_events, bundle_path)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    node_by_id = {node["evidence_id"]: node for node in nodes}

    events = [
        {
            "id": node["evidence_id"],
            "ts": _relative_seconds(node),
            "domain": _domain_from_node(node),
            "label": _short_label(node),
            "merge_group": _merge_group(node),
            "confidence": node.get("confidence", 1.0),
            "lane": node.get("lane", ""),
            "source": node.get("source", ""),
            "source_type": node.get("source_type", ""),
            "message": node.get("message", ""),
            "clock_domain": node.get("clock_domain", "unknown"),
            "attributes": node.get("attributes", {}),
        }
        for node in nodes
    ]

    # Causal connections (cause -> effect) derived from the real evidence graph.
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src not in node_by_id or tgt not in node_by_id:
            # Never emit an edge that cannot be anchored to a rendered node.
            continue
        connections.append(
            {
                "source": src,
                "target": tgt,
                "provenance": edge.get("provenance", "unknown"),
                "type": "causal_edge",
            }
        )

    # Append causality violations as marked edges
    for violation in temporal_result.get("causality_violations", []):
        a = violation.get("event_a", "")
        b = violation.get("event_b", "")
        connections.append(
            {
                "source": a,
                "target": b,
                "type": "violation",
                "confidence": violation.get("confidence", 0),
                "description": violation.get("violation", ""),
            }
        )

    # Anomalies as anomaly markers
    for anom in temporal_result.get("temporal_anomalies", []):
        for eid in anom.get("affected_events", []):
            anomaly_points.append(
                {
                    "id": eid,
                    "type": anom.get("type", "unknown"),
                    "severity": anom.get("severity", 0.5),
                    "confidence": anom.get("confidence", 0.5),
                    "explanation": anom.get("explanation", ""),
                }
            )

    # Time loops
    for loop in temporal_result.get("time_loops", []):
        loop_events = loop.get("events", [])
        for i in range(len(loop_events)):
            src = loop_events[i]
            tgt = loop_events[(i + 1) % len(loop_events)]
            connections.append(
                {
                    "source": src,
                    "target": tgt,
                    "type": "loop_edge",
                    "loop_id": loop.get("loop_id"),
                    "confidence": loop.get("confidence", 0.5),
                }
            )

    # Untrusted windows as timeline bands
    untrusted_bands = []
    for win in temporal_result.get("untrusted_windows", []):
        untrusted_bands.append(
            {
                "start_s": win.get("start_s", 0),
                "end_s": win.get("end_s", 0),
                "reason": win.get("type", "unknown"),
                "description": win.get("description", "") or win.get("violation", ""),
            }
        )

    causal_chains = _build_causal_chains(nodes, edges)
    lanes, lane_edges = _build_lane_topology(nodes, edges)

    return {
        "events": events,
        "connections": connections,
        "anomaly_points": anomaly_points,
        "untrusted_bands": untrusted_bands,
        "causal_chains": causal_chains,
        "lanes": lanes,
        "lane_edges": lane_edges,
        "summary": {
            "total_events": len(events),
            "connections": len(connections),
            "anomaly_count": len(anomaly_points),
            "time_loop_count": sum(1 for c in connections if c.get("type") == "loop_edge"),
            "is_anomalous": temporal_result.get("is_time_anomalous", False),
            "confidence": temporal_result.get("temporal_confidence_score", 1.0),
            "causal_edge_count": sum(
                1 for c in connections if c.get("type") == "causal_edge"
            ),
            "violation_count": sum(
                1 for c in connections if c.get("type") == "violation"
            ),
            "provenance_breakdown": _provenance_breakdown(connections),
            "chain_count": len(causal_chains),
            "lane_count": len(lanes),
        },
    }


def _build_lane_topology(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Aggregate the evidence graph into lanes and the edges between lanes.

    The evidence graph has one node per timeline event (51 for the golden
    incident) and 112 edges, which is a hairball to draw. The lanes are the
    system's own logical stages (``cloud_requests``, ``detection_publication``,
    ``tf_events``, ...) and the causal edges between them define a much
    smaller DAG that a human can actually read. The lane tier is the longest
    path from a lane root, computed from the real edges.
    """
    lane_of = {n["evidence_id"]: n.get("lane", "") for n in nodes}
    lane_events: Dict[str, List[Dict[str, Any]]] = {}
    for node in nodes:
        lane_events.setdefault(node.get("lane", ""), []).append(node)

    lane_pairs: Dict[Tuple[str, str], int] = {}
    lane_provenance: Dict[Tuple[str, str], Dict[str, int]] = {}
    for edge in edges:
        src = lane_of.get(edge.get("source", ""))
        tgt = lane_of.get(edge.get("target", ""))
        if src is None or tgt is None or src == tgt:
            continue
        key = (src, tgt)
        lane_pairs[key] = lane_pairs.get(key, 0) + 1
        prov = edge.get("provenance", "unknown")
        counts = lane_provenance.setdefault(key, {})
        counts[prov] = counts.get(prov, 0) + 1

    # Longest-path tier over the lane DAG (iterative, cycle-safe).
    parents: Dict[str, set] = {}
    for src_lane, tgt_lane in lane_pairs:
        parents.setdefault(tgt_lane, set()).add(src_lane)
        parents.setdefault(src_lane, set())

    level: Dict[str, int] = {}
    for lane in parents:
        prefix: List[str] = []
        seen: set = set()
        cur = lane
        while cur is not None and cur not in level:
            if cur in seen:
                break  # cycle: stop and treat as resolved at its current tier
            seen.add(cur)
            prefix.append(cur)
            next_lane = None
            for candidate in parents.get(cur, ()):
                if candidate not in level and candidate not in seen:
                    next_lane = candidate
                    break
            cur = next_lane
        for name in reversed(prefix):
            if name in level:
                continue
            parent_levels = [
                level[p] for p in parents.get(name, ()) if p in level
            ]
            level[name] = (max(parent_levels) + 1) if parent_levels else 0

    lanes = []
    for lane, lane_nodes in lane_events.items():
        ordered = sorted(lane_nodes, key=lambda n: n.get("timestamp_ns", 0))
        lanes.append(
            {
                "lane": lane,
                "tier": level.get(lane, 0),
                "event_count": len(lane_nodes),
                "domains": sorted({n.get("clock_domain", "unknown") for n in lane_nodes}),
                "sources": sorted({n.get("source", "") for n in lane_nodes}),
                "start_s": ordered[0].get("relative_ts_s", 0),
                "end_s": ordered[-1].get("relative_ts_s", 0),
                "first_message": ordered[0].get("message", ""),
                "last_message": ordered[-1].get("message", ""),
            }
        )
    lanes.sort(key=lambda item: (item["tier"], item["lane"]))

    lane_edges = []
    for (src, tgt), count in lane_pairs.items():
        lane_edges.append(
            {
                "source": src,
                "target": tgt,
                "edge_count": count,
                "provenance": lane_provenance.get((src, tgt), {}),
            }
        )
    lane_edges.sort(key=lambda edge_item: (level.get(str(edge_item["source"]), 0), str(edge_item["target"])))

    return lanes, lane_edges


def _build_causal_chains(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Extract the real propagation paths that terminate in a safety outcome.

    ``deployment_chain`` edges link the deployment to *every* later event,
    which is a horizon marker rather than a propagation step; keeping them
    turns the graph into a hairball. The chains below walk the informative
    edges (ordering, handoff, proximity) and report the longest path into
    each terminal safety node, which is the actual causal storyline.
    """
    node_by_id = {n["evidence_id"]: n for n in nodes}
    parents: Dict[str, List[Dict[str, Any]]] = {}
    children: Dict[str, List[Dict[str, Any]]] = {}

    for edge in edges:
        if edge.get("provenance") == "deployment_chain":
            continue
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src not in node_by_id or tgt not in node_by_id:
            continue
        parents.setdefault(tgt, []).append(edge)
        children.setdefault(src, []).append(edge)

    def longest_path_to(node_id: str) -> List[Dict[str, Any]]:
        """
        Longest path into ``node_id`` over the informative subgraph.

        Iterative post-order walk so a deep evidence chain cannot exhaust the
        interpreter's recursion limit.
        """
        best_path: Dict[str, List[Dict[str, Any]]] = {}
        on_stack: Set[str] = set()
        stack: List[Tuple[str, bool]] = [(node_id, False)]

        while stack:
            current, expanded = stack.pop()
            if expanded:
                on_stack.discard(current)
                best: List[Dict[str, Any]] = []
                for edge in parents.get(current, []):
                    src = edge["source"]
                    if src in on_stack:
                        continue  # cycle guard
                    candidate = best_path.get(src, [])
                    if len(candidate) + 1 > len(best):
                        best = candidate + [edge]
                best_path[current] = best
                continue

            if current in best_path or current in on_stack:
                continue
            on_stack.add(current)
            stack.append((current, True))
            for edge in parents.get(current, []):
                src = edge["source"]
                if src not in best_path and src not in on_stack:
                    stack.append((src, False))

        return best_path.get(node_id, [])

    chains = []
    for node in nodes:
        node_id = node["evidence_id"]
        if children.get(node_id):
            continue  # not a terminal node
        path = longest_path_to(node_id)
        if not path:
            continue
        steps = []
        for edge in path:
            src = node_by_id[edge["source"]]
            tgt = node_by_id[edge["target"]]
            steps.append(
                {
                    "source": src["evidence_id"],
                    "target": tgt["evidence_id"],
                    "provenance": edge.get("provenance", "unknown"),
                    "source_lane": src.get("lane", ""),
                    "target_lane": tgt.get("lane", ""),
                    "source_message": src.get("message", ""),
                    "target_message": tgt.get("message", ""),
                }
            )
        terminal = node_by_id[path[-1]["target"]]
        chains.append(
            {
                "terminal_id": terminal["evidence_id"],
                "terminal_lane": terminal.get("lane", ""),
                "terminal_message": terminal.get("message", ""),
                "terminal_source": terminal.get("source", ""),
                "terminal_domain": terminal.get("clock_domain", "unknown"),
                "is_safety_outcome": _is_safety_outcome(terminal, node_by_id),
                "length": len(steps),
                "steps": steps,
            }
        )

    chains.sort(key=lambda c: (c["is_safety_outcome"], c["length"]), reverse=True)
    return chains


def _is_safety_outcome(
    terminal: Dict[str, Any],
    node_by_id: Dict[str, Any],
) -> bool:
    """Mark terminals that represent an actual safety/interlock failure."""
    lane = terminal.get("lane", "")
    message = terminal.get("message", "").lower()
    if lane == "safety_state":
        return True
    keywords = ("emergency stop", "estop", "safety", "interlock", "halt")
    return any(k in message for k in keywords)


def _resolve_evidence_graph(
    temporal_result: Dict[str, Any],
    original_events: List[Dict[str, Any]],
    bundle_path: Optional[Path],
) -> Dict[str, Any]:
    """
    Return the evidence graph, re-deriving it if the temporal result lacks one.

    Temporal results restored from a report written before the graph existed
    have no ``evidence_graph``; re-deriving keeps the visualization real
    instead of silently rendering an empty graph.
    """
    graph = temporal_result.get("evidence_graph")
    if graph and graph.get("nodes"):
        return graph

    if not original_events:
        return {"nodes": [], "edges": []}

    try:
        from cauveris.temporal.evidence import extract_from_timeline
        from cauveris.temporal.integration import _flatten_attributes

        evidence = extract_from_timeline(original_events, bundle_path)
    except Exception:  # pragma: no cover - defensive: never break the endpoint
        logger.exception("Failed to re-derive evidence graph for visualization")
        return {"nodes": [], "edges": []}

    nodes = []
    edges = []
    base_ns = min((ev.timestamp_ns for ev in evidence), default=0)
    for ev in evidence:
        nodes.append(
            {
                "evidence_id": ev.evidence_id,
                "timestamp_ns": ev.timestamp_ns,
                "relative_ts_s": round((ev.timestamp_ns - base_ns) / 1e9, 3),
                "lane": ev.lane,
                "source": ev.source,
                "source_type": ev.source_type,
                "message": ev.message,
                "clock_domain": ev.clock_domain.value
                if hasattr(ev.clock_domain, "value")
                else str(ev.clock_domain),
                "confidence": float(ev.extra.get("confidence", 0.0) or 0.0),
                "status": ev.extra.get("status", ""),
                "attributes": _flatten_attributes(ev.extra.get("attributes", {})),
            }
        )
        for child_id, prov in ev.child_provenance.items():
            edges.append(
                {
                    "source": ev.evidence_id,
                    "target": child_id,
                    "provenance": prov.value if hasattr(prov, "value") else str(prov),
                }
            )

    return {"nodes": nodes, "edges": edges}


def _provenance_breakdown(connections: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for conn in connections:
        if conn.get("type") != "causal_edge":
            continue
        prov = conn.get("provenance", "unknown")
        counts[prov] = counts.get(prov, 0) + 1
    return counts


def _relative_seconds(node: Dict[str, Any]) -> float:
    """Position a node on the relative timeline (seconds from incident start)."""
    if "relative_ts_s" in node:
        return node["relative_ts_s"]
    ts_ns = node.get("timestamp_ns", 0)
    return round(ts_ns / 1e9, 3)


def _domain_from_node(node: Dict[str, Any]) -> str:
    """Extract a short domain label from an evidence node."""
    domain = node.get("clock_domain", "")
    if domain and domain != "unknown":
        return domain
    source_type = node.get("source_type", "")
    if source_type == "otel_trace":
        return "cloud"
    if source_type in ("jsonl_log", "text_log"):
        lane = node.get("lane", "")
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


def _short_label(node: Dict[str, Any]) -> str:
    """Get a short label for an event."""
    msg = node.get("message", "")
    if len(msg) > 60:
        return msg[:57] + "..."
    return msg


def _merge_group(node: Dict[str, Any]) -> Optional[str]:
    """Get a group key for events that should be rendered together."""
    source = node.get("source", "")
    ts_ns = node.get("timestamp_ns", 0)
    # Group by source file and millisecond
    return f"{source}@{ts_ns // 1_000_000}"

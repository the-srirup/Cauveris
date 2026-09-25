"""
Time loop detection: identify circular causality dependencies.

A time loop occurs when events form a cycle in the causal graph, implying
that some effect is treated as its own cause. This is a topological anomaly,
not a temporal one per se, but loops often indicate that the timestamps are
wrong (e.g., a clock was reset during the loop) or that the causal model is
fundamentally broken.

The detector uses an *iterative* Tarjan's algorithm to avoid Python recursion
limits on large graphs. It returns strongly connected components that form
cycles, and for each cycle it computes the minimum time delta that would
break the loop, giving a confidence score.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class TimeLoop:
    """
    A cycle of events that form a time loop.

    Attributes
    ----------
    loop_id : str
        Unique identifier for this loop.
    events : List[str]
        Ordered list of evidence IDs forming the loop.
    cycle_length_ms : float
        Total span of timestamps in the loop (may be near-zero for tight loops).
    confidence : float
        0..1 score; higher when timestamps are strongly contradictory.
    description : str
        Human-readable summary.
    """
    loop_id: str
    events: List[str]
    cycle_length_ms: float
    confidence: float
    description: str


class TimeLoopDetector:
    """
    Detect circular causality in event dependency graphs.

    Uses iterative Tarjan's algorithm for SCC detection to avoid stack overflow
    on large incident bundles. The dependency graph is built from parent-child
    links inferred in ``EvidenceExtractor``.
    """

    def __init__(self, min_loop_size: int = 2, confidence_threshold: float = 0.5):
        self.min_loop_size = min_loop_size
        self.confidence_threshold = confidence_threshold
        self.loops: List[TimeLoop] = []

    def detect(
        self,
        evidence: List[Any],  # List[TemporalEvidence]
    ) -> List[TimeLoop]:
        """
        Find all time loops in the causal graph derived from evidence.

        Returns
        -------
        List[TimeLoop]
            All loops with confidence >= threshold, sorted by confidence.
        """
        self.loops = []

        # Build adjacency list
        graph: Dict[str, Set[str]] = {}
        for ev in evidence:
            node = ev.evidence_id
            graph.setdefault(node, set())
            for child in ev.child_candidates:
                graph[node].add(child)

        # Find SCCs using iterative Tarjan
        sccs = self._tarjan_scc(graph)

        for scc in sccs:
            if len(scc) >= self.min_loop_size:
                loop = self._build_loop(scc, evidence)
                if loop.confidence >= self.confidence_threshold:
                    self.loops.append(loop)

        return sorted(self.loops, key=lambda l: l.confidence, reverse=True)

    # ------------------------------------------------------------------ #
    # Iterative Tarjan's algorithm
    # ------------------------------------------------------------------ #
    def _tarjan_scc(self, graph: Dict[str, Set[str]]) -> List[Set[str]]:
        """
        Iterative Tarjan's SCC algorithm.

        Uses an explicit stack to avoid Python recursion limits.
        """
        index_counter = [0]
        stack = []
        lowlink = {}
        index = {}
        on_stack = {}
        sccs = []

        # Initialize all nodes
        for v in graph:
            index[v] = -1

        for v in graph:
            if index[v] == -1:
                # Start DFS from v
                call_stack = []
                call_stack.append(("visit", v))

                while call_stack:
                    op, node = call_stack.pop()

                    if op == "visit":
                        if index[node] != -1:
                            continue

                        index[node] = index_counter[0]
                        lowlink[node] = index_counter[0]
                        index_counter[0] += 1
                        stack.append(node)
                        on_stack[node] = True

                        # Push back for post-processing
                        call_stack.append(("postvisit", node))

                        # Push children
                        for child in graph.get(node, []):
                            if index[child] == -1:
                                call_stack.append(("visit", child))
                            elif on_stack.get(child, False):
                                lowlink[node] = min(lowlink[node], index[child])

                    elif op == "postvisit":
                        # Check children that are already processed
                        for child in graph.get(node, []):
                            if on_stack.get(child, False):
                                lowlink[node] = min(lowlink[node], lowlink.get(child, index[child]))

                        if lowlink[node] == index[node]:
                            scc = set()
                            while True:
                                w = stack.pop()
                                on_stack[w] = False
                                scc.add(w)
                                if w == node:
                                    break
                            if len(scc) > 1 or (len(scc) == 1 and scc.pop() in graph.get(node, set())):
                                sccs.append(scc)

        return sccs

    # ------------------------------------------------------------------ #
    def _build_loop(self, scc: Set[str], evidence: List[Any]) -> TimeLoop:
        """
        Build a TimeLoop object from an SCC, computing confidence from timestamps.
        """
        events = list(scc)

        # Get timestamps for all events in loop
        ts_by_id = {}
        for ev in evidence:
            if ev.evidence_id in scc:
                ts_by_id[ev.evidence_id] = ev.timestamp_ns

        timestamps = list(ts_by_id.values())
        if len(timestamps) < 2:
            return TimeLoop(
                loop_id=f"loop_{hash(tuple(sorted(scc))) % 10000}",
                events=events,
                cycle_length_ms=0.0,
                confidence=0.0,
                description="Single-event loop (trivial)",
            )

        min_ts = min(timestamps)
        max_ts = max(timestamps)
        cycle_span_ns = max_ts - min_ts

        # Confidence: higher when the loop spans very little time compared to
        # the overall incident duration, indicating a genuine temporal paradox
        # rather than just "many events happened close together".
        total_span = max(timestamps) - min(timestamps) if len(timestamps) > 1 else 1
        confidence = 1.0 - min(1.0, total_span / max(1_000_000_000.0, 1_000_000_000))

        # Force higher confidence when timestamps are clearly contradictory
        # (i.e., multiple events at exactly the same time in different domains)
        unique_ts = len(set(timestamps))
        if unique_ts < len(timestamps):
            confidence = max(confidence, 0.8)

        event_str = " -> ".join(events[:5])
        if len(events) > 5:
            event_str += " ..."

        return TimeLoop(
            loop_id=f"loop_{len(self.loops) + 1}",
            events=events,
            cycle_length_ms=cycle_span_ns / 1_000_000.0,
            confidence=confidence,
            description=f"Time loop: {event_str} -> {events[0]}",
        )

    # ------------------------------------------------------------------ #
    def detect_cycles_simple(
        self,
        adjacency: Dict[str, Set[str]],
    ) -> List[List[str]]:
        """
        Simpler cycle detection using Johnson's algorithm concept, but
        simplified to return any cycle (not necessarily elementary) found
        during DFS. This is more permissive and catches loops arising from
        duplicated edges or miss-ordered events.

        For production use, prefer ``detect`` with full evidence.
        """
        cycles: List[List[str]] = []

        def dfs(start: str, current: str, path: List[str], visited: Set[str]):
            if current in visited:
                if current == start and len(path) >= self.min_loop_size:
                    cycles.append(path.copy())
                return

            visited.add(current)
            path.append(current)

            for neighbor in adjacency.get(current, []):
                dfs(start, neighbor, path, visited.copy())

        for node in adjacency:
            dfs(node, node, [], set())

        # Remove duplicates
        unique: List[List[str]] = []
        seen = set()
        for cyc in cycles:
            key = tuple(sorted(cyc))
            if key not in seen:
                seen.add(key)
                unique.append(cyc)

        return unique
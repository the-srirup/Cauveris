"""
Recovering *which* mechanism broke an incident, from the evidence alone.

The analysis layer used to answer "the data was stale" and nothing else.  A
stale frame is a **symptom**: an out-of-memory kill, a dependency that
stopped answering and a lock that never became available all present the
same way to an operator watching the robot.  The difference matters because
the remediations are incompatible - raising a timeout does nothing for a
process that was killed for using too much memory, and giving a worker pool
more room does nothing for a dependency that is down.

This module reads the mechanism out of the incident's own evidence:

* the **logs** say what broke ("OOMKilled", "request timed out after 500 ms",
  "lock wait timeout"),
* the **configuration** declares the envelope the workload ran in (a memory
  limit, a request deadline, a lock timeout),
* the **metrics** say how much the workload actually needed.

Nothing here knows an incident id, a file name or a message format.  The
patterns match the *words* operators and runtimes use regardless of the
vendor that emitted them, which is what lets the same code read a ROS node's
log and a cloud service's log.

The output is a :class:`FailureEvidence`, which the system model turns into
twin parameters.  Where a number cannot be measured, the smallest value
consistent with the evidence is used and the assumption is recorded in
``sources`` - an unbounded "the model guesses" is worse than a stated
"the model knows the working set exceeded the ceiling, and not by how much".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .parameter_registry import FailureFamily, FailureMechanism

logger = logging.getLogger(__name__)

__all__ = [
    "FailureEvidence",
    "extract_failure_evidence",
    "extract_all_mechanisms",
    "classify_log_records",
    "MEMORY_NEEDLES",
    "TIMEOUT_NEEDLES",
    "LOCK_NEEDLES",
    "matches_any",
]


# ---------------------------------------------------------------------------
# The words an incident uses
# ---------------------------------------------------------------------------
#
# The needles are shared with the hypothesis layer, so the hypothesis that
# names a mechanism and the model that reproduces it cannot drift apart.

#: An exhausted memory envelope.
MEMORY_NEEDLES: Tuple[str, ...] = (
    r"out\s*of\s*memory",
    r"oomkilled",
    r"oom[-_ ]kill",
    r"\boom\b",
    r"memoryerror",
    r"memory\s*limit",
    r"memory\s*(?:exceeded|exhausted|over)",
    r"exceeded\s+(?:its\s+|the\s+)?(?:memory|heap|ram)",
    r"cgroup",
    r"heap\s*space",
    r"allocation\s+failed",
    r"cannot\s+allocate\s+memory",
    r"killed\s+process",
    r"resource\s*exhaust",
)

#: A dependency that did not answer in time.
TIMEOUT_NEEDLES: Tuple[str, ...] = (
    r"timed?\s*out",
    r"time(?:d)?\s*out",
    r"timeout",
    r"deadline\s+exceeded",
    r"context\s+deadline",
    r"read\s+timed",
    r"etimedout",
    r"econnreset",
    r"connection\s+refused",
    r"connection\s+reset",
    r"upstream\s+(?:unavailable|timed)",
)

#: A shared resource that could not be acquired.
LOCK_NEEDLES: Tuple[str, ...] = (
    r"deadlock",
    r"lock\s*timeout",
    r"lock\s*contention",
    r"lock\s*wait",
    r"contended\s+lock",
    r"mutex",
    r"semaphore",
    r"pool\s+exhausted",
    r"thread\s+starvation",
    r"starved\s+(?:pool|thread)",
)


def matches_any(text: str, needles: Sequence[str]) -> bool:
    """Whether ``text`` contains any of the given patterns."""
    if not text:
        return False
    for needle in needles:
        if re.search(needle, text, re.IGNORECASE):
            return True
    return False


# ---------------------------------------------------------------------------
# Numbers in the evidence
# ---------------------------------------------------------------------------

#: Byte units, expressed in mebibytes.
_MEMORY_UNITS: Dict[str, float] = {
    "b": 1.0 / (1024.0 * 1024.0),
    "kb": 1.0 / 1024.0,
    "kib": 1.0 / 1024.0,
    "mb": 1.0,
    "mib": 1.0,
    "gb": 1024.0,
    "gib": 1024.0,
    "tb": 1024.0 * 1024.0,
}

#: Time units, expressed in milliseconds.
_TIME_UNITS: Dict[str, float] = {
    "ns": 1e-6,
    "us": 1e-3,
    "µs": 1e-3,
    "ms": 1.0,
    "msec": 1.0,
    "millis": 1.0,
    "milliseconds": 1.0,
    "s": 1000.0,
    "sec": 1000.0,
    "secs": 1000.0,
    "second": 1000.0,
    "seconds": 1000.0,
}

#: ``memory limit of 512 MiB``, ``heap cap: 2 GB``, ``ram quota 256MB``.
#:
#: The number has to follow the limit keyword directly - optionally through
#: "of", "is", "was" or a colon.  Without that binding the pattern reads
#: "memory limit exceeded (used 1400 MB of 512 MiB)" as a limit of 1400 MB,
#: which is the working set rather than the ceiling.
_MEMORY_LIMIT_RE = re.compile(
    r"(?:memory|heap|ram|mem|rss|container)"
    r"[\w .\-]{0,24}?"
    r"(?:limit|quota|cap|ceiling|budget|allowance)"
    r"(?:\s*(?:of|is|was|:|=)\s*)?"
    r"(\d+(?:[.,]\d+)?)\s*([kmgt]i?b)\b",
    re.IGNORECASE,
)

#: ``peak memory usage 1536 MB``, ``resident set 1.4 GiB``.
_MEMORY_USAGE_RE = re.compile(
    r"(?:peak|used|usage|using|consumed|consuming|resident|rss|heap|working\s*set|memory)"
    r"[^0-9\n]{0,28}?"
    r"(\d+(?:[.,]\d+)?)\s*([kmgt]i?b)\b",
    re.IGNORECASE,
)

#: ``timed out after 500 ms``, ``request timeout of 2 s``.
_TIMEOUT_RE = re.compile(
    r"(?:timed?\s*out|timeout|time\s*out|deadline)"
    r"[^0-9\n]{0,24}?"
    r"(\d+(?:[.,]\d+)?)\s*(ms|msec|milliseconds|s|sec|secs|seconds)\b",
    re.IGNORECASE,
)

#: ``lock timeout after 1000 ms``.
_LOCK_TIMEOUT_RE = re.compile(
    r"(?:lock|mutex|semaphore)[^0-9\n]{0,24}?"
    r"(?:timed?\s*out|timeout|wait(?:ed|ing)?\s+for)"
    r"[^0-9\n]{0,20}?"
    r"(\d+(?:[.,]\d+)?)\s*(ms|msec|milliseconds|s|sec|secs|seconds)\b",
    re.IGNORECASE,
)

#: ``lock held for 1400 ms``, ``mutex wait 250 ms``.
_LOCK_HOLD_RE = re.compile(
    r"(?:lock|mutex|semaphore|critical\s*section)[^0-9\n]{0,32}?"
    r"(?:held|hold\s*time|duration|acquired|wait(?:ed)?\s+(?:for|on))"
    r"[^0-9\n]{0,20}?"
    r"(\d+(?:[.,]\d+)?)\s*(ms|msec|milliseconds|s|sec|secs|seconds)\b",
    re.IGNORECASE,
)

#: A log record that describes a request being served.  Used as the
#: denominator when counting how often a lock was contended.
_REQUEST_NEEDLES: Tuple[str, ...] = (
    r"\brequest\b",
    r"\bresponse\b",
    r"\bcall\b",
    r"\bhandled\b",
    r"\bserved\b",
    r"\bin[- ]?flight\b",
    r"\bbatch\b",
    r"\binference\b",
)


def _to_number(raw: str) -> Optional[float]:
    try:
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _memory_mb(raw: str, unit: str) -> Optional[float]:
    value = _to_number(raw)
    if value is None:
        return None
    factor = _MEMORY_UNITS.get(str(unit).lower())
    if factor is None:
        return None
    return value * factor


def _milliseconds(raw: str, unit: str) -> Optional[float]:
    value = _to_number(raw)
    if value is None:
        return None
    factor = _TIME_UNITS.get(str(unit).lower())
    if factor is None:
        return None
    return value * factor


def _spans(pattern: re.Pattern, text: str) -> List[Tuple[int, int]]:
    return [match.span() for match in pattern.finditer(text)]


def _overlaps(span: Tuple[int, int], others: Iterable[Tuple[int, int]]) -> bool:
    start, end = span
    for other_start, other_end in others:
        if start < other_end and other_start < end:
            return True
    return False


def _memory_limit_from_text(text: str) -> Optional[float]:
    """The memory ceiling mentioned in a piece of text, in mebibytes."""
    best: Optional[float] = None
    for match in _MEMORY_LIMIT_RE.finditer(text):
        value = _memory_mb(match.group(1), match.group(2))
        if value is None or value <= 0:
            continue
        best = value if best is None else max(best, value)
    return best


def _memory_demand_from_text(text: str) -> Optional[float]:
    """
    The peak working set mentioned in a piece of text, in mebibytes.

    Numbers that belong to a *limit* are excluded: "exceeded its memory limit
    of 512 MiB" states the ceiling, not the usage, and reading it as the
    demand would put the workload exactly at the ceiling rather than above
    it.
    """
    limit_spans = _spans(_MEMORY_LIMIT_RE, text)
    best: Optional[float] = None
    for match in _MEMORY_USAGE_RE.finditer(text):
        if _overlaps(match.span(), limit_spans):
            continue
        value = _memory_mb(match.group(1), match.group(2))
        if value is None or value <= 0:
            continue
        best = value if best is None else max(best, value)
    return best


def _timeout_candidates(text: str) -> List[float]:
    """Every timeout mentioned in a piece of text, in milliseconds."""
    found: List[float] = []
    for match in _TIMEOUT_RE.finditer(text):
        value = _milliseconds(match.group(1), match.group(2))
        if value is None or value <= 0:
            continue
        found.append(value)
    return found


def _timeout_from_text(text: str) -> Optional[float]:
    """
    The deadline a piece of text states, in milliseconds.

    The *tightest* bound is taken: when a record says "request timeout of
    200 ms exceeded after 500 ms", the deadline was 200 ms and the call had
    been running for 500 ms when it was abandoned.  Reading the largest
    number as the deadline would let a call that ran for twice its budget
    pass as compliant.
    """
    candidates = _timeout_candidates(text)
    return min(candidates) if candidates else None


def _observed_latency_from_text(text: str) -> Optional[float]:
    """
    How long a cancelled call had been running, in milliseconds.

    The longest stated elapsed time is the lower bound on the latency the
    request actually reached: it was still in flight then.
    """
    candidates = _timeout_candidates(text)
    return max(candidates) if candidates else None


def _lock_timeout_from_text(text: str) -> Optional[float]:
    best: Optional[float] = None
    for match in _LOCK_TIMEOUT_RE.finditer(text):
        value = _milliseconds(match.group(1), match.group(2))
        if value is None or value <= 0:
            continue
        best = value if best is None else max(best, value)
    return best


def _lock_hold_from_text(text: str) -> Optional[float]:
    best: Optional[float] = None
    for match in _LOCK_HOLD_RE.finditer(text):
        value = _milliseconds(match.group(1), match.group(2))
        if value is None or value <= 0:
            continue
        best = value if best is None else max(best, value)
    return best


#: Metric columns and series that report a working set.
_MEMORY_METRIC_NEEDLES: Tuple[str, ...] = (
    "memory",
    "rss",
    "heap",
    "resident",
    "working_set",
    "working set",
    "oom",
    "usage",
    "used",
)

#: Words that mean a column is *not* a working set: it is the capacity, the
#: headroom, a ratio or a count.  ``memory_total_mb`` is what the machine
#: has; ``memory_used_mb`` is what the workload needed, and only the second
#: one is the demand the twin has to compare against the ceiling.
_MEMORY_METRIC_EXCLUSIONS: Tuple[str, ...] = (
    "total",
    "free",
    "available",
    "limit",
    "quota",
    "capacity",
    "size",
    "count",
    "percent",
    "pct",
    "utilization",
    "util",
    "swap",
    "cache",
    "buffer",
    "clock",
)


def _demand_from_metrics(metrics: Dict[str, List[Any]]) -> Tuple[Optional[float], Optional[str]]:
    """
    The peak working set the metrics report.

    Returns the value in mebibytes and the series it came from.  Columns
    that state the capacity rather than the use - the machine's total
    memory, the free memory, a utilisation percentage - are ignored: a
    "memory" series that reads 8192 next to a "memory used" series that
    reads 3584 describes a machine with 8 GiB and a workload that needed
    3.5 GiB, and the workload is the demand.
    """
    best: Optional[float] = None
    best_source: Optional[str] = None
    for series_name, samples in (metrics or {}).items():
        for sample in samples or []:
            values = getattr(sample, "values", None) or {}
            for column, value in values.items():
                label = f"{series_name} {column}".lower()
                if not any(needle in label for needle in _MEMORY_METRIC_NEEDLES):
                    continue
                if any(needle in label for needle in _MEMORY_METRIC_EXCLUSIONS):
                    continue
                number = _to_number(str(value))
                if number is None or number <= 1.0:
                    continue
                megabytes = number
                if "bytes" in label or label.endswith("_b"):
                    # A metric that states its unit in the name is converted
                    # rather than skipped: the Prometheus exporters report a
                    # working set in bytes, and a byte count is a working set,
                    # not a capacity.
                    megabytes = number / (1024.0 * 1024.0)
                elif "gb" in label or "gib" in label:
                    megabytes = number * 1024.0
                elif "kb" in label or "kib" in label:
                    megabytes = number / 1024.0
                elif "mb" in label or "mib" in label:
                    megabytes = number
                if best is None or megabytes > best:
                    best = megabytes
                    best_source = f"metric:{series_name}:{column}"
    return best, best_source


# ---------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------


@dataclass
class FailureEvidence:
    """
    What the evidence says about the mechanism that broke the incident.

    Attributes:
        mechanism: The canonical mechanism name.
        family: The failure family the mechanism belongs to.
        parameters: The twin parameters the mechanism needs, with the values
            the evidence supports.
        sources: Where each parameter came from.  A source that describes an
            assumption says so in words, so a reader can tell a measurement
            from an inference.
        signals: How many records supported each reading.
        observations: Quantitative facts that are evidence but not twin
            parameters - the latency a cancelled call had reached, for
            instance.
        summary: One sentence an operator can read.
        confidence: How strongly the evidence supports the mechanism.
    """

    mechanism: str
    family: str
    parameters: Dict[str, float] = field(default_factory=dict)
    sources: Dict[str, str] = field(default_factory=dict)
    signals: Dict[str, int] = field(default_factory=dict)
    observations: Dict[str, float] = field(default_factory=dict)
    summary: str = ""
    confidence: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "mechanism": self.mechanism,
            "family": self.family,
            "parameters": dict(self.parameters),
            "sources": dict(self.sources),
            "signals": dict(self.signals),
            "observations": dict(self.observations),
            "summary": self.summary,
            "confidence": round(self.confidence, 3),
        }


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _config_parameter(
    config: Dict[str, Any], parameter: str
) -> Tuple[Optional[float], Optional[str]]:
    """
    The value a configuration declares for a parameter.

    The lookup goes through the parameter registry's needle matching, so the
    analysis layer and the verifier resolve a key to the same parameter -
    ``resources.memory_limit_mb`` is understood exactly as well as
    ``memory_limit_mb``.
    """
    from .parameters import match_parameter  # local import: avoids a cycle

    for key, value in (config or {}).items():
        if match_parameter(key) != parameter:
            continue
        number = _to_number(str(value))
        if number is None:
            continue
        return number, str(key)
    return None, None


def _records(bundle: Any) -> List[Any]:
    return list(getattr(bundle, "logs", []) or [])


def _text_of(record: Any) -> str:
    return str(getattr(record, "text", "") or "")


def _level_of(record: Any) -> str:
    return str(getattr(record, "level", "INFO") or "INFO").upper()


def _classify_records(records: Sequence[Any]) -> Dict[str, List[Any]]:
    """
    Assign every log record to the mechanism it speaks about.

    A record that mentions a lock belongs to the lock mechanism even when it
    also says "timeout": ``lock wait timeout after 1000 ms`` is a lock
    contention, not a dependency timeout, and counting it as both would let a
    patch that fixes one mechanism look as though it fixed the other.
    """
    buckets: Dict[str, List[Any]] = {
        FailureMechanism.LOCK_CONTENTION: [],
        FailureMechanism.RESOURCE_EXHAUSTION: [],
        FailureMechanism.DEPENDENCY_TIMEOUT: [],
    }
    for record in records:
        text = _text_of(record)
        if not text:
            continue
        if matches_any(text, LOCK_NEEDLES):
            buckets[FailureMechanism.LOCK_CONTENTION].append(record)
        elif matches_any(text, MEMORY_NEEDLES):
            buckets[FailureMechanism.RESOURCE_EXHAUSTION].append(record)
        elif matches_any(text, TIMEOUT_NEEDLES):
            buckets[FailureMechanism.DEPENDENCY_TIMEOUT].append(record)
    return buckets


def _weighted_signal(records: Sequence[Any]) -> float:
    """How much weight a set of records carries as evidence."""
    score = 0.0
    for record in records:
        level = _level_of(record)
        score += 2.0 if level in ("CRITICAL", "FATAL") else 1.5 if level == "ERROR" else 1.0
    return score


def extract_failure_evidence(
    bundle: Any, *, only: Optional[Sequence[str]] = None
) -> Optional[FailureEvidence]:
    """
    Read the failure mechanism out of an incident bundle.

    Args:
        bundle: The loaded :class:`~cauveris.analysis.evidence.EvidenceBundle`.
        only: Restrict the reading to these mechanisms.  Used when a caller
            wants the evidence for one family - the hypothesis layer builds a
            competing hypothesis per family, and each needs the numbers for
            *its* family rather than for whichever family happens to be the
            strongest.

    Returns:
        The evidence for the dominant mechanism, or ``None`` when the
        bundle's logs do not name a mechanism at all.  A bundle with no
        mechanism is not a failure of this function - it is a latency
        incident, which the pipeline reports as a latency incident.
    """
    if bundle is None:
        return None

    records = _records(bundle)
    if not records:
        return None

    wanted = set(only) if only else None

    def _wanted(mechanism: str) -> bool:
        return wanted is None or mechanism in wanted

    buckets = _classify_records(records)
    config = dict(getattr(bundle, "config", {}) or {})
    metrics = dict(getattr(bundle, "metrics", {}) or {})

    candidates: List[Tuple[float, str, FailureEvidence]] = []

    # --- resource exhaustion ------------------------------------------------
    memory_records = buckets[FailureMechanism.RESOURCE_EXHAUSTION]
    if memory_records and _wanted(FailureMechanism.RESOURCE_EXHAUSTION):
        limit, limit_source = _config_parameter(config, "resource_limit_mb")
        demand: Optional[float] = None
        demand_source: Optional[str] = None

        if limit is None:
            for record in memory_records:
                limit = _memory_limit_from_text(_text_of(record))
                if limit is not None:
                    limit_source = f"log:{getattr(record, 'source', '?')}"
                    break
        if limit is None:
            for record in records:
                limit = _memory_limit_from_text(_text_of(record))
                if limit is not None:
                    limit_source = f"log:{getattr(record, 'source', '?')}"
                    break

        measured_demand, metric_source = _demand_from_metrics(metrics)
        if measured_demand is not None:
            demand = measured_demand
            demand_source = metric_source
        else:
            for record in records:
                found = _memory_demand_from_text(_text_of(record))
                if found is not None and (demand is None or found > demand):
                    demand = found
                    demand_source = f"log:{getattr(record, 'source', '?')}"

        parameters: Dict[str, float] = {}
        sources: Dict[str, str] = {}
        if limit is not None:
            parameters["resource_limit_mb"] = limit
            sources["resource_limit_mb"] = f"declared:{limit_source}"
        if demand is not None:
            parameters["resource_demand_mb"] = demand
            sources["resource_demand_mb"] = f"measured:{demand_source}"
        elif limit is not None:
            # The process was killed for exceeding its ceiling, so the
            # working set was strictly above it.  How far above is not
            # recorded anywhere in the bundle, so the smallest value
            # consistent with the evidence is used.
            parameters["resource_demand_mb"] = limit * 1.05
            sources["resource_demand_mb"] = (
                f"inferred:the process was killed for exceeding {limit:.0f} MiB, "
                "so the working set was above the ceiling; the margin is the "
                "smallest one consistent with that fact"
            )

        score = _weighted_signal(memory_records)
        if limit is not None:
            score += 2.0
        if demand is not None:
            score += 2.0
        evidence = FailureEvidence(
            mechanism=FailureMechanism.RESOURCE_EXHAUSTION,
            family=FailureFamily.RESOURCE_EXHAUSTION,
            parameters=parameters,
            sources=sources,
            signals={"records": len(memory_records)},
            summary=(
                f"The workload exceeded its resource envelope ({len(memory_records)} "
                "log record(s) report memory exhaustion) and the requests it was "
                "serving were lost."
            ),
            confidence=_confidence(score, len(memory_records)),
        )
        candidates.append((score, FailureMechanism.RESOURCE_EXHAUSTION, evidence))

    # --- dependency timeout -------------------------------------------------
    timeout_records = buckets[FailureMechanism.DEPENDENCY_TIMEOUT]
    if timeout_records and _wanted(FailureMechanism.DEPENDENCY_TIMEOUT):
        deadline, deadline_source = _config_parameter(config, "request_timeout_ms")
        observed: Optional[float] = None
        if deadline is None:
            for record in timeout_records:
                observed = _timeout_from_text(_text_of(record))
                if observed is not None:
                    deadline = observed
                    deadline_source = f"log:{getattr(record, 'source', '?')}"
                    break
        else:
            for record in timeout_records:
                found = _observed_latency_from_text(_text_of(record))
                if found is not None:
                    observed = found
                    break
        if observed is None:
            observed = deadline

        parameters = {}
        sources = {}
        if deadline is not None:
            parameters["request_timeout_ms"] = deadline
            sources["request_timeout_ms"] = f"declared:{deadline_source}"

        observations: Dict[str, float] = {}
        if observed is not None:
            # The call was abandoned when it reached the deadline, so the
            # real latency was at least this long.  It is not a parameter -
            # it is a floor the model has to reach.
            observations["observed_failure_latency_ms"] = observed

        score = _weighted_signal(timeout_records)
        if deadline is not None:
            score += 2.0
        evidence = FailureEvidence(
            mechanism=FailureMechanism.DEPENDENCY_TIMEOUT,
            family=FailureFamily.DEPENDENCY_TIMEOUT,
            parameters=parameters,
            sources=sources,
            signals={"records": len(timeout_records)},
            observations=observations,
            summary=(
                f"A dependency did not answer inside the caller's deadline "
                f"({len(timeout_records)} log record(s) report a timeout), so the "
                "request was cancelled and its work discarded."
            ),
            confidence=_confidence(score, len(timeout_records)),
        )
        candidates.append((score, FailureMechanism.DEPENDENCY_TIMEOUT, evidence))

    # --- lock contention ----------------------------------------------------
    lock_records = buckets[FailureMechanism.LOCK_CONTENTION]
    if lock_records and _wanted(FailureMechanism.LOCK_CONTENTION):
        lock_timeout, lock_timeout_source = _config_parameter(config, "lock_timeout_ms")
        if lock_timeout is None:
            for record in lock_records:
                lock_timeout = _lock_timeout_from_text(_text_of(record))
                if lock_timeout is not None:
                    lock_timeout_source = f"log:{getattr(record, 'source', '?')}"
                    break

        hold: Optional[float] = None
        hold_source: Optional[str] = None
        for record in lock_records:
            found = _lock_hold_from_text(_text_of(record))
            if found is not None and (hold is None or found > hold):
                hold = found
                hold_source = f"log:{getattr(record, 'source', '?')}"

        # How often a request had to wait for the lock.  The denominator is
        # the number of records that describe a request being served: the
        # ratio of contended requests to all requests.
        request_records = [
            record for record in records if matches_any(_text_of(record), _REQUEST_NEEDLES)
        ]
        denominator = len(request_records) or len(records)
        contention = min(1.0, len(lock_records) / denominator) if denominator else 0.0

        parameters = {}
        sources = {}
        if lock_timeout is not None:
            parameters["lock_timeout_ms"] = lock_timeout
            sources["lock_timeout_ms"] = f"declared:{lock_timeout_source}"
        if hold is not None:
            parameters["lock_hold_ms"] = hold
            sources["lock_hold_ms"] = f"measured:{hold_source}"
        elif lock_timeout is not None:
            # The wait timed out, so the lock was held for longer than the
            # caller was willing to wait.  The bundle does not say how much
            # longer, so the smallest consistent hold is used.
            parameters["lock_hold_ms"] = lock_timeout * 1.05
            sources["lock_hold_ms"] = (
                f"inferred:the acquire timed out after {lock_timeout:.0f} ms, so the "
                "lock was held for longer than that; the margin is the smallest one "
                "consistent with that fact"
            )
        if contention > 0.0:
            parameters["lock_contention_prob"] = contention
            sources["lock_contention_prob"] = (
                f"measured:{len(lock_records)} of {denominator} record(s) report "
                "lock contention"
            )

        score = _weighted_signal(lock_records)
        if lock_timeout is not None:
            score += 2.0
        if hold is not None:
            score += 1.0
        evidence = FailureEvidence(
            mechanism=FailureMechanism.LOCK_CONTENTION,
            family=FailureFamily.LOCK_CONTENTION,
            parameters=parameters,
            sources=sources,
            signals={"records": len(lock_records)},
            summary=(
                f"Concurrent workers serialised on a shared resource "
                f"({len(lock_records)} log record(s) report lock contention), so the "
                "requests behind them stopped being served."
            ),
            confidence=_confidence(score, len(lock_records)),
        )
        candidates.append((score, FailureMechanism.LOCK_CONTENTION, evidence))

    if not candidates:
        return None

    # The strongest reading wins.  Ties are broken by an explicit order so
    # that the same bundle always yields the same mechanism.
    order = {
        FailureMechanism.RESOURCE_EXHAUSTION: 0,
        FailureMechanism.LOCK_CONTENTION: 1,
        FailureMechanism.DEPENDENCY_TIMEOUT: 2,
    }
    candidates.sort(key=lambda item: (-item[0], order.get(item[1], 9)))
    return candidates[0][2]


def classify_log_records(bundle: Any) -> Dict[str, List[Any]]:
    """
    The log records of a bundle, grouped by the mechanism each one speaks about.

    This is the *same* classification the evidence reader uses, exposed so
    that the hypothesis layer cannot reach a different conclusion from the
    model.  A record that mentions a lock is a lock record even when it also
    says "timeout"; a hypothesis layer that re-matched the raw text would
    offer a patch for a timeout the incident never had.
    """
    return _classify_records(_records(bundle))


def extract_all_mechanisms(bundle: Any) -> Dict[str, FailureEvidence]:
    """
    The evidence for every mechanism the bundle's logs speak about.

    The hypothesis layer builds a competing hypothesis per family, and each
    hypothesis needs the numbers for *its* family - the memory ceiling for a
    memory hypothesis, the acquire deadline for a lock hypothesis.  Reading
    only the dominant mechanism would leave the others without numbers.

    Returns:
        Mapping of mechanism name -> its evidence.  Empty when the bundle
        names no mechanism at all.
    """
    found: Dict[str, FailureEvidence] = {}
    for mechanism in (
        FailureMechanism.RESOURCE_EXHAUSTION,
        FailureMechanism.DEPENDENCY_TIMEOUT,
        FailureMechanism.LOCK_CONTENTION,
    ):
        evidence = extract_failure_evidence(bundle, only=(mechanism,))
        if evidence is not None:
            found[mechanism] = evidence
    return found


def _confidence(score: float, records: int) -> float:
    """A confidence in the range 0..1 from the weight of the evidence."""
    if records <= 0:
        return 0.0
    return max(0.0, min(0.95, 0.4 + 0.1 * min(records, 5) + 0.05 * min(score, 4.0)))

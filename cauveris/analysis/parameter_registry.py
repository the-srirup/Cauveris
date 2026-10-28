"""
The registry of parameters the pipeline can simulate, and therefore patch.

The project used to carry the same list in three places:

* ``cauveris/analysis/parameters.py::PARAMETER_NEEDLES`` - which
  configuration key controls which parameter,
* ``cauveris/simulation/mapping.py::TWIN_PARAMETERS`` - which parameters the
  twin will accept an intervention for,
* ``cauveris/verifier/workspace.py::_TWIN_PARAMETER_NEEDLES`` - a third copy
  of the first list.

Because the three lists drifted apart, a knob had to be added to all of them
before it could be fixed, and anything not on the list was silently
unfixable.  That is why the project could diagnose a memory exhaustion
incident and then offer no repair for it.

This module is the single source of truth.  Everything else derives from it,
so adding a parameter here makes it simulatable, patchable and verifiable at
once - there is no second list to keep in step.

A parameter declares:

* **what it is** - its unit, its admissible range, a description,
* **which failure family it belongs to** - so an intervention can be checked
  against the family that produced the hypothesis,
* **which configuration keys control it** - matched on the *shape* of the
  key, so ``resources.memory_limit_mb`` is understood as readily as
  ``memory_limit_mb``,
* **whether it is patchable** - a parameter measured from the evidence
  (``resource_demand_mb``) is a fact about the incident and cannot be
  changed by a patch; a parameter declared by the configuration
  (``resource_limit_mb``) can.

The module deliberately imports nothing from the rest of the package, so it
can be used from the analysis, simulation and verification layers without
creating an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

__all__ = [
    "FailureFamily",
    "FailureMechanism",
    "ParameterSpec",
    "PARAMETER_REGISTRY",
    "FAMILY_PARAMETERS",
    "PATCHABLE_PARAMETERS",
    "SIMULATABLE_PARAMETERS",
    "spec_for",
    "parameters_for_family",
    "needles_for",
    "MEMORY_NEEDLES",
    "TIMEOUT_NEEDLES",
    "LOCK_NEEDLES",
    "DB_POOL_NEEDLES",
    "QUEUE_OVERFLOW_NEEDLES",
    "TRANSPORT_NEEDLES",
    "WORKER_SATURATION_NEEDLES",
    "CLOCK_SKEW_NEEDLES",
    "ARRIVAL_OVERLOAD_NEEDLES",
    "MECHANISM_NEEDLES",
    "MECHANISM_FAMILY",
    "MECHANISM_PRIORITY",
]


class FailureMechanism:
    """
    The mechanisms by which a request can fail outright.

    A mechanism is what actually happened; a symptom is what the operator
    saw.  The two are not interchangeable: an out-of-memory kill and a
    dependency timeout both present as "the robot stopped", and only one of
    them is fixed by raising a timeout.  The names live here so that the
    analysis layer, the simulation layer and the verification layer all
    count the same mechanism under the same name.
    """

    #: The workload exceeded the resource envelope it was given.
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    #: The dependency did not answer inside the caller's deadline.
    DEPENDENCY_TIMEOUT = "dependency_timeout"
    #: A shared resource could not be acquired in time.
    LOCK_CONTENTION = "lock_contention"
    #: A distributed database or storage connection pool was exhausted.
    CONNECTION_POOL_EXHAUSTION = "connection_pool_exhaustion"
    #: A bounded queue or buffer overflowed, and the excess was dropped.
    QUEUE_OVERFLOW_BACKPRESSURE = "queue_overflow_backpressure"
    #: Samples were lost or badly delayed in transit between two hosts.
    TRANSPORT_LOSS_JITTER = "transport_loss_jitter"
    #: Every worker in the pool was busy, so work had to wait.
    WORKER_SATURATION = "worker_saturation"
    #: The clocks of two hosts disagree, so an arrival is misjudged.
    CLOCK_SKEW = "clock_skew"
    #: Work arrives faster than the service can complete it.
    ARRIVAL_OVERLOAD = "arrival_overload"
    #: The frame arrived, but too late to be acted on.  This is not a lost
    #: request - the request completed - so it is not one of the mechanisms
    #: above; it is the symptom the pipeline has always reported.
    CONTROL_DEADLINE_MISSED = "control_deadline_missed"

    ALL = (
        RESOURCE_EXHAUSTION,
        DEPENDENCY_TIMEOUT,
        LOCK_CONTENTION,
        CONNECTION_POOL_EXHAUSTION,
        QUEUE_OVERFLOW_BACKPRESSURE,
        TRANSPORT_LOSS_JITTER,
        WORKER_SATURATION,
        CLOCK_SKEW,
        ARRIVAL_OVERLOAD,
    )

    #: The mechanisms the digital twin can actually reproduce.
    #:
    #: A mechanism that is not twin-backed may still be *diagnosed* - the
    #: evidence reader recognises it - but no simulation can demonstrate that
    #: a proposed repair clears it, so the platform refuses to certify a
    #: patch for it.  Claiming a verified repair for a mechanism the twin
    #: cannot reproduce would be a fabrication.
    TWIN_BACKED = (
        RESOURCE_EXHAUSTION,
        DEPENDENCY_TIMEOUT,
        LOCK_CONTENTION,
        CONNECTION_POOL_EXHAUSTION,
        QUEUE_OVERFLOW_BACKPRESSURE,
        TRANSPORT_LOSS_JITTER,
        WORKER_SATURATION,
        CLOCK_SKEW,
        ARRIVAL_OVERLOAD,
    )


class FailureFamily:
    """
    The families of failure the analysis layer can model.

    A family is a *mechanism*, not a symptom.  Memory exhaustion, a
    dependency timeout and lock contention all present as "the request did
    not complete in time", which is why one mechanism - resource pressure
    and deadline misses - models all three honestly.
    """

    #: The request arrived, but too late to be used.
    LATENCY = "latency"
    #: The request failed because the workload exceeded its resource limit.
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    #: The request failed because a dependency did not answer in time.
    DEPENDENCY_TIMEOUT = "dependency_timeout"
    #: The request failed because a shared resource could not be acquired.
    LOCK_CONTENTION = "lock_contention"
    #: The request failed because a distributed database or storage pool was exhausted.
    DATABASE_STORAGE = "database_storage"
    #: Samples were lost between the producer and the consumer.
    TRANSPORT = "transport"
    #: The clocks of two hosts disagree.
    TIME_BASE = "time_base"
    #: The producer offers work faster than the consumer takes it.
    ARRIVAL = "arrival"
    #: The service itself is slow.
    SERVICE = "service"
    #: The subscriber discards samples before they are used.
    SUBSCRIBER = "subscriber"

    ALL = (
        LATENCY,
        RESOURCE_EXHAUSTION,
        DEPENDENCY_TIMEOUT,
        LOCK_CONTENTION,
        DATABASE_STORAGE,
        TRANSPORT,
        TIME_BASE,
        ARRIVAL,
        SERVICE,
        SUBSCRIBER,
    )


@dataclass(frozen=True)
class ParameterSpec:
    """One parameter the pipeline can simulate."""

    name: str
    unit: str
    family: str
    default: float
    minimum: float
    maximum: float
    description: str
    #: Fragments of a configuration key name that identify this parameter.
    #: Matched case-insensitively against the key's last dotted component and
    #: against the full dotted path.
    needles: Tuple[str, ...] = ()
    #: Fragments that *disqualify* a key from matching this parameter.
    #:
    #: Several deadlines live in the same configuration and they are not
    #: interchangeable: a control loop's deadline is the watchdog budget, a
    #: transform lookup's deadline belongs to another subsystem, and neither is
    #: the deadline a caller puts on the request.  Treating them as the same
    #: knob would let a patch shorten a safety budget, so a key that names
    #: one of them is excluded explicitly.
    excluded_needles: Tuple[str, ...] = ()
    #: Whether a patch may change this parameter.  A parameter that is
    #: *measured* describes the incident and is not a knob.
    patchable: bool = True
    #: Whether the parameter is measured from the evidence rather than
    #: declared by the configuration.
    measured: bool = False

    @property
    def is_configurable(self) -> bool:
        """Whether this parameter comes from the bundle's configuration."""
        return self.patchable and not self.measured


#: Every parameter the pipeline understands, keyed by name.
PARAMETER_REGISTRY: Dict[str, ParameterSpec] = {}


def _add(spec: ParameterSpec) -> ParameterSpec:
    PARAMETER_REGISTRY[spec.name] = spec
    return spec


# ---------------------------------------------------------------------------
# Latency family - the perception pipeline's timing knobs
# ---------------------------------------------------------------------------

_add(
    ParameterSpec(
        name="batching_window_ms",
        unit="ms",
        family=FailureFamily.LATENCY,
        default=100.0,
        minimum=0.0,
        maximum=2000.0,
        description="How long the inference server waits for a batch to fill.",
        needles=("batching_window", "batch_window", "batching_delay", "batch_timeout"),
    )
)

_add(
    ParameterSpec(
        name="max_batch_size",
        unit="items",
        family=FailureFamily.LATENCY,
        default=8.0,
        minimum=1.0,
        maximum=1024.0,
        description="The largest batch the inference server will process at once.",
        needles=("max_batch_size", "batch_size", "max_batch"),
    )
)

_add(
    ParameterSpec(
        name="qos_queue_depth",
        unit="samples",
        family=FailureFamily.SUBSCRIBER,
        default=1.0,
        minimum=1.0,
        maximum=4096.0,
        description="How many samples the subscriber buffers before dropping the oldest.",
        needles=("qos_depth", "queue_depth"),
    )
)

_add(
    ParameterSpec(
        name="consumer_rate_hz",
        unit="Hz",
        family=FailureFamily.SUBSCRIBER,
        default=10.0,
        minimum=0.01,
        maximum=1000.0,
        description="The rate at which the control loop samples the subscriber.",
        needles=(
            "consumer_rate",
            "control_rate",
            "control_frequency",
            "control_hz",
            "publish_rate",
        ),
    )
)

_add(
    ParameterSpec(
        name="transport_mean_ms",
        unit="ms",
        family=FailureFamily.TRANSPORT,
        default=5.0,
        minimum=0.0,
        maximum=5000.0,
        description="The mean delay of the link between producer and consumer.",
        needles=("transport_mean", "link_latency", "network_latency"),
    )
)

_add(
    ParameterSpec(
        name="transport_sigma_ms",
        unit="ms",
        family=FailureFamily.TRANSPORT,
        default=1.0,
        minimum=0.0,
        maximum=2000.0,
        description="The spread of the transport delay.",
        needles=("transport_sigma", "link_jitter", "network_jitter"),
    )
)

_add(
    ParameterSpec(
        name="transport_loss_prob",
        unit="probability",
        family=FailureFamily.TRANSPORT,
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="The probability that a sample is lost in transit.",
        needles=("transport_loss", "packet_loss", "loss_rate", "drop_rate"),
    )
)

_add(
    ParameterSpec(
        name="server_workers",
        unit="workers",
        family=FailureFamily.ARRIVAL,
        default=1.0,
        minimum=1.0,
        maximum=256.0,
        description="How many requests the server can serve concurrently.",
        needles=(
            "server_workers",
            "worker_count",
            "num_workers",
            "n_workers",
            "pool_size",
            "thread_count",
        ),
    )
)

_add(
    ParameterSpec(
        name="arrival_rate_hz",
        unit="Hz",
        family=FailureFamily.ARRIVAL,
        default=10.0,
        minimum=0.01,
        maximum=10000.0,
        description="The rate at which requests arrive at the service.",
        needles=("arrival_rate", "sensor_rate", "frame_rate"),
    )
)

_add(
    ParameterSpec(
        name="clock_skew_ms",
        unit="ms",
        family=FailureFamily.TIME_BASE,
        default=0.0,
        minimum=-10000.0,
        maximum=10000.0,
        description="The offset between the clocks of the producer and the consumer.",
        needles=("clock_skew",),
    )
)

_add(
    ParameterSpec(
        name="service_base_ms",
        unit="ms",
        family=FailureFamily.SERVICE,
        default=10.0,
        minimum=0.0,
        maximum=10000.0,
        description="The fixed cost of serving a batch, independent of its size.",
        needles=("service_base", "inference_base"),
    )
)

_add(
    ParameterSpec(
        name="service_per_item_ms",
        unit="ms/item",
        family=FailureFamily.SERVICE,
        default=5.0,
        minimum=0.0,
        maximum=5000.0,
        description="The marginal cost of serving one more item in a batch.",
        needles=("service_per_item", "per_item"),
    )
)

# ---------------------------------------------------------------------------
# Resource-exhaustion family
#
# The workload runs inside a resource envelope - a container memory limit, a
# cgroup ceiling, a JVM heap cap.  ``resource_limit_mb`` is the envelope;
# ``resource_demand_mb`` is the working set the workload actually needs,
# measured from the incident.  The ratio of the two is the pressure the
# service runs under.
# ---------------------------------------------------------------------------

_add(
    ParameterSpec(
        name="resource_limit_mb",
        unit="MiB",
        family=FailureFamily.RESOURCE_EXHAUSTION,
        default=0.0,
        minimum=0.0,
        maximum=1048576.0,
        description="The resource envelope the workload is allowed to use.",
        needles=(
            "memory_limit",
            "mem_limit",
            "heap_limit",
            "heap_size",
            "max_heap",
            "memory_quota",
            "container_memory",
            "max_size_mb",
            "ram_limit",
        ),
    )
)

_add(
    ParameterSpec(
        name="resource_demand_mb",
        unit="MiB",
        family=FailureFamily.RESOURCE_EXHAUSTION,
        default=0.0,
        minimum=0.0,
        maximum=1048576.0,
        description="The working set the workload needs at its busiest.",
        needles=(),
        patchable=False,
        measured=True,
    )
)

_add(
    ParameterSpec(
        name="resource_pressure_penalty_ms",
        unit="ms",
        family=FailureFamily.RESOURCE_EXHAUSTION,
        default=0.0,
        minimum=0.0,
        maximum=100000.0,
        description="The extra service time incurred at full resource pressure.",
        needles=(),
        patchable=False,
        measured=True,
    )
)

# ---------------------------------------------------------------------------
# Dependency-timeout family
#
# A caller that cannot wait forever gives its dependency a deadline.  A
# dependency that does not answer in time does not make the caller slow, it
# makes the call *fail*.
# ---------------------------------------------------------------------------

_add(
    ParameterSpec(
        name="request_timeout_ms",
        unit="ms",
        family=FailureFamily.DEPENDENCY_TIMEOUT,
        default=0.0,
        minimum=0.0,
        maximum=600000.0,
        description="The deadline the client gives the request.",
        needles=(
            "request_timeout",
            "upstream_timeout",
            "read_timeout",
            "connect_timeout",
            "response_timeout",
            "deadline_ms",
            "timeout_ms",
        ),
        excluded_needles=(
            # The control loop's deadline is the watchdog budget, not a
            # request deadline: the twin already models it separately, and
            # shortening it would disarm the safety system.
            "control_loop",
            "control_deadline",
            "watchdog",
            # The freshness budget is the safety budget.
            "freshness",
            "staleness",
            "max_age",
            # A transform lookup belongs to another subsystem; its deadline
            # does not bound the request this pipeline serves.
            "transform",
            # A lock deadline is a *different* deadline.  The needle
            # ``timeout_ms`` is a substring of ``lock_timeout_ms``, and
            # specificity ordering alone does not separate them, so a
            # lock deadline read as a request deadline would have the
            # wrong remediation attached to it.
            "lock",
            "mutex",
            "acquire",
        ),
    )
)

# ---------------------------------------------------------------------------
# Lock-contention family
#
# Concurrent workers can serialise on a shared resource.  The wait is only
# fatal when the caller has a deadline for acquiring it.
# ---------------------------------------------------------------------------

_add(
    ParameterSpec(
        name="lock_timeout_ms",
        unit="ms",
        family=FailureFamily.LOCK_CONTENTION,
        default=0.0,
        minimum=0.0,
        maximum=600000.0,
        description="How long a caller waits for a contended lock before abandoning it.",
        needles=(
            "lock_timeout",
            "lock_wait",
            "mutex_timeout",
            "acquire_timeout",
        ),
    )
)

_add(
    ParameterSpec(
        name="lock_hold_ms",
        unit="ms",
        family=FailureFamily.LOCK_CONTENTION,
        default=0.0,
        minimum=0.0,
        maximum=600000.0,
        description="How long a contended lock is held before it is released.",
        needles=(),
        patchable=False,
        measured=True,
    )
)

_add(
    ParameterSpec(
        name="lock_contention_prob",
        unit="probability",
        family=FailureFamily.LOCK_CONTENTION,
        default=0.0,
        minimum=0.0,
        maximum=1.0,
        description="The probability that a request has to wait for a contended lock.",
        needles=(),
        patchable=False,
        measured=True,
    )
)

# ---------------------------------------------------------------------------
# Database and distributed storage connection pool family
# ---------------------------------------------------------------------------

_add(
    ParameterSpec(
        name="db_pool_size",
        unit="connections",
        family=FailureFamily.DATABASE_STORAGE,
        default=0.0,
        minimum=0.0,
        maximum=65536.0,
        description="Connection pool capacity for distributed database or storage.",
        needles=(
            "db_pool_size",
            "max_connections",
            "max_pool_size",
            "max_active",
            "pool_size",
            "pool_max",
            "max_total",
        ),
    )
)

_add(
    ParameterSpec(
        name="db_connection_timeout_ms",
        unit="ms",
        family=FailureFamily.DATABASE_STORAGE,
        default=0.0,
        minimum=0.0,
        maximum=600000.0,
        description="Timeout when acquiring a connection from the database connection pool.",
        needles=(
            "db_connection_timeout",
            "checkout_timeout",
            "connection_timeout_ms",
            "pool_timeout",
        ),
    )
)

_add(
    ParameterSpec(
        name="db_demand_connections",
        unit="connections",
        family=FailureFamily.DATABASE_STORAGE,
        default=0.0,
        minimum=0.0,
        maximum=65536.0,
        description="The peak concurrent connection demand observed during the incident.",
        needles=(),
        patchable=False,
        measured=True,
    )
)


#: Parameters grouped by the failure family they remediate.
FAMILY_PARAMETERS: Dict[str, Tuple[str, ...]] = {}
for _spec in PARAMETER_REGISTRY.values():
    FAMILY_PARAMETERS.setdefault(_spec.family, ())
    FAMILY_PARAMETERS[_spec.family] += (_spec.name,)


#: Parameters a patch may change.
PATCHABLE_PARAMETERS: Tuple[str, ...] = tuple(
    name for name, spec in PARAMETER_REGISTRY.items() if spec.is_configurable
)

#: Parameters the twin will accept an intervention for.
SIMULATABLE_PARAMETERS: Tuple[str, ...] = tuple(PARAMETER_REGISTRY.keys())


def spec_for(name: str) -> ParameterSpec:
    """The specification of ``name``.

    Raises:
        KeyError: when the parameter is not registered.
    """
    return PARAMETER_REGISTRY[name]


def parameters_for_family(family: str) -> Tuple[str, ...]:
    """Every parameter that remediates ``family``."""
    return FAMILY_PARAMETERS.get(family, ())


def needles_for(names: Tuple[str, ...]) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """
    The ``(parameter, needles)`` pairs for the given parameters.

    The pairs are ordered so that a more specific parameter is matched
    before a more general one: ``lock_timeout_ms`` has to be checked before
    ``request_timeout_ms``, or a lock deadline would be read as a request
    deadline.  Specificity is judged by the length of the needle, so the
    ordering does not have to be maintained by hand.
    """
    pairs = []
    for name in names:
        spec = PARAMETER_REGISTRY.get(name)
        if spec is None or not spec.needles:
            continue
        pairs.append((name, spec.needles))

    pairs.sort(key=lambda item: -max(len(needle) for needle in item[1]))
    return tuple(pairs)


# ---------------------------------------------------------------------------
# The vocabulary of mechanisms
# ---------------------------------------------------------------------------
#
# The words an incident uses to describe its own failure.  These needle sets
# live here, beside the parameter registry, because they are the other half
# of the same contract: the parameter registry says *which knob* remediates a
# family, and this table says *which words* name that family in a log.
#
# They used to live in ``failure_evidence.py`` and in a second, parallel
# module for the mechanism detectors.  The two copies drifted - the
# detector's lock pattern did not match ``lock wait timeout``, so a bundle
# whose log said exactly that was diagnosed as a dependency timeout - and a
# bundle that one copy recognised and the other did not was refused a
# repair the pipeline could perform.  One copy removes that class of bug.

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
    r"allocation\s*failed",
    r"cannot\s+allocate\s*memory",
    r"killed\s*process",
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
)

#: An exhausted database or distributed storage connection pool.
DB_POOL_NEEDLES: Tuple[str, ...] = (
    r"connection\s*pool\s*(?:exhausted|timeout|full|limit)",
    r"timeout:\s*pool\s*exhausted",
    r"too\s*many\s*connections",
    r"remaining\s*connection\s*slots",
    r"connection\s*(?:checkout|acquisition)\s*timeout",
    r"hikari.*(?:timeout|unavailable|is not available)",
    r"max_connections\s*exceeded",
    r"db\s*pool\s*(?:exhausted|full)",
    r"cannot\s+get\s+connection",
)

#: A bounded queue or buffer that overflowed.
QUEUE_OVERFLOW_NEEDLES: Tuple[str, ...] = (
    r"queue\s*(?:overfl|full)",
    r"buffer\s*overfl",
    r"backpressure",
    r"rejectedexecutionexception",
    r"dropped\s*(?:message|frame|sample|item)",
    r"inbox\s*full",
    r"too\s*many\s*(?:frames|messages|samples)\s*queued",
    r"oldest\s+(?:retained\s+)?(?:frame|sample|message)\s*is\s*stale",
    r"consumer\s*(?:buffer|queue)\s*full",
)

#: Samples lost or delayed in transit between two hosts.
TRANSPORT_NEEDLES: Tuple[str, ...] = (
    r"packet\s*loss",
    r"packet\s*drop",
    r"retransmit",
    r"network\s*jitter",
    r"transport\s*(?:error|loss|delay)",
    r"dropped\s*packets?",
    r"excessive\s+transport",
    r"link\s*(?:latency|jitter|loss)",
    r"econnreset",
)

#: Every worker in the pool was busy.
WORKER_SATURATION_NEEDLES: Tuple[str, ...] = (
    r"worker\s*pool\s*saturated",
    r"workers?\s+busy",
    r"all\s*\d+\s*workers?\s+busy",
    r"max_workers\s*reached",
    r"pool\s*exhausted",
    r"thread\s*pool\s*exhausted",
    r"no\s*free\s*workers?",
    r"worker\s*starvation",
    r"requests?\s*queued\s+behind",
)

#: The clocks of two hosts disagree.
CLOCK_SKEW_NEEDLES: Tuple[str, ...] = (
    r"clock\s*skew",
    r"time\s*drift",
    r"ntp\s*(?:sync|offset|unsynchron)",
    r"timestamp\s+in\s+the\s+future",
    r"clock\s*unsynchron",
    r"ptp\s*offset",
    r"hosts?\s+disagree\s+about\s+the\s+time",
)

#: Work arrives faster than the service completes it.
ARRIVAL_OVERLOAD_NEEDLES: Tuple[str, ...] = (
    r"rate\s*limit\s*exceeded",
    r"traffic\s*spike",
    r"too\s+many\s+requests",
    r"\b429\b",
    r"queue\s*depth\s*increas",
    r"queue\s*rising",
    r"backlog\s*accumulat",
    r"(?:arrival|ingress|inflow)\s*rate\s*exceed",
    r"overload(?:ed)?",
)


#: The needle set that names each mechanism, keyed by mechanism id.
#:
#: This is the single answer to "which words mean this mechanism".  The
#: evidence reader, the hypothesis layer and the mechanism detectors all
#: consult it, so a log line cannot be an OOM to one and a timeout to
#: another.
MECHANISM_NEEDLES: Dict[str, Tuple[str, ...]] = {
    FailureMechanism.RESOURCE_EXHAUSTION: MEMORY_NEEDLES,
    FailureMechanism.DEPENDENCY_TIMEOUT: TIMEOUT_NEEDLES,
    FailureMechanism.LOCK_CONTENTION: LOCK_NEEDLES,
    FailureMechanism.CONNECTION_POOL_EXHAUSTION: DB_POOL_NEEDLES,
    FailureMechanism.QUEUE_OVERFLOW_BACKPRESSURE: QUEUE_OVERFLOW_NEEDLES,
    FailureMechanism.TRANSPORT_LOSS_JITTER: TRANSPORT_NEEDLES,
    FailureMechanism.WORKER_SATURATION: WORKER_SATURATION_NEEDLES,
    FailureMechanism.CLOCK_SKEW: CLOCK_SKEW_NEEDLES,
    FailureMechanism.ARRIVAL_OVERLOAD: ARRIVAL_OVERLOAD_NEEDLES,
}


#: The family each mechanism belongs to.
MECHANISM_FAMILY: Dict[str, str] = {
    FailureMechanism.RESOURCE_EXHAUSTION: FailureFamily.RESOURCE_EXHAUSTION,
    FailureMechanism.DEPENDENCY_TIMEOUT: FailureFamily.DEPENDENCY_TIMEOUT,
    FailureMechanism.LOCK_CONTENTION: FailureFamily.LOCK_CONTENTION,
    FailureMechanism.CONNECTION_POOL_EXHAUSTION: FailureFamily.DATABASE_STORAGE,
    FailureMechanism.QUEUE_OVERFLOW_BACKPRESSURE: FailureFamily.SUBSCRIBER,
    FailureMechanism.TRANSPORT_LOSS_JITTER: FailureFamily.TRANSPORT,
    FailureMechanism.WORKER_SATURATION: FailureFamily.ARRIVAL,
    FailureMechanism.CLOCK_SKEW: FailureFamily.TIME_BASE,
    FailureMechanism.ARRIVAL_OVERLOAD: FailureFamily.ARRIVAL,
}


#: Which mechanism wins when one log record could name several.
#:
#: The precedence is not alphabetical and not a matter of confidence.  A
#: dependency timeout is the *broadest* signal in the set - almost every
#: other failure eventually mentions a timeout on its way out - so it ranks
#: last.  A lock is more specific than a timeout ("lock wait timeout after
#: 100 ms" is contention, not a slow dependency), and a saturated worker
#: pool is more specific still.  Ranking them explicitly is what stops a
#: bundle whose worker pool ran dry from being reported as a slow
#: dependency, and therefore from being "repaired" by raising a timeout that
#: was never the problem.
MECHANISM_PRIORITY: Dict[str, int] = {
    FailureMechanism.CONNECTION_POOL_EXHAUSTION: 0,
    FailureMechanism.LOCK_CONTENTION: 1,
    FailureMechanism.RESOURCE_EXHAUSTION: 2,
    FailureMechanism.WORKER_SATURATION: 3,
    FailureMechanism.QUEUE_OVERFLOW_BACKPRESSURE: 4,
    FailureMechanism.ARRIVAL_OVERLOAD: 5,
    FailureMechanism.TRANSPORT_LOSS_JITTER: 6,
    FailureMechanism.CLOCK_SKEW: 7,
    FailureMechanism.DEPENDENCY_TIMEOUT: 8,
}

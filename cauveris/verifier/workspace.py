"""
Reading a verification workspace.

The verifier works on a copy of the *real* incident bundle: the configuration
files and the source files the bundle actually shipped.  This module reads
that copy back, so the checks downstream (the twin, the safety comparison, the
rollback comparison) all look at the same bytes that the patch produced.

Nothing here knows an incident id or a file name.  The mapping from a
configuration key to a pipeline parameter is made from the *shape* of the key,
so a bundle that calls its batching window ``dynamic_batching.max_delay_ms``
is understood exactly as well as one that calls it ``batching_window_ms``.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

#: Source directories copied out of the bundle into the verification
#: workspace.  Paths inside these directories keep their bundle-relative
#: names, so a diff against ``config/inference.yaml`` applies to the copy.
WORKSPACE_SOURCE_DIRS = ("config", "source", "deploy", "tests", "scripts")

#: A configuration key maps onto a pipeline parameter when its name contains
#: one of these needles.  The order matters: the first match wins, so the
#: specific names are checked before the general ones.
_TWIN_PARAMETER_NEEDLES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "batching_window_ms",
        ("batching_window", "batch_window", "batching_delay", "batch_timeout"),
    ),
    ("max_batch_size", ("max_batch_size", "batch_size", "max_batch")),
    ("qos_queue_depth", ("qos_depth", "queue_depth")),
    (
        "server_workers",
        ("server_workers", "worker_count", "num_workers", "n_workers", "pool_size", "thread_count"),
    ),
    (
        "consumer_rate_hz",
        ("consumer_rate", "control_rate", "control_frequency", "control_hz", "publish_rate"),
    ),
    ("arrival_rate_hz", ("arrival_rate", "sensor_rate", "frame_rate")),
    ("transport_mean_ms", ("transport_mean", "link_latency", "network_latency")),
    ("transport_sigma_ms", ("transport_sigma", "link_jitter", "network_jitter")),
    ("service_base_ms", ("service_base", "inference_base")),
    ("service_per_item_ms", ("service_per_item", "per_item")),
    ("clock_skew_ms", ("clock_skew",)),
)

#: Boolean configuration keys that arm a safety behaviour.  A key that was
#: ``true`` in the bundle must still be ``true`` after a patch: turning a
#: watchdog off is not a fix, it is the incident.
_SAFETY_ENABLE_NEEDLES = (
    "emergency_stop",
    "e_stop",
    "estop",
    "watchdog",
    "fail_safe",
    "failsafe",
    "interlock",
    "guard",
    "safety",
    "collision_avoid",
    "obstacle_stop",
    "stale_stop",
)

#: Numeric configuration keys that express a safety limit.  A patch may lower
#: one, but never raise it: raising a budget or a timeout removes the
#: constraint the incident violated.
_SAFETY_LIMIT_NEEDLES = (
    "freshness_budget",
    "staleness_budget",
    "max_age",
    "max_staleness",
    "safety_budget",
    "max_latency",
    "deadline",
    "watchdog_timeout",
    "friction",
    "braking",
    "decel",
    "safety_margin",
    "stopping_distance",
)

#: Assignment patterns in source files, e.g. ``self.qos_depth = 10``.
_SOURCE_ASSIGNMENT_RE = re.compile(
    r"(?m)^\s*(?:self\.)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(?P<value>-?\d+(?:\.\d+)?)\s*$"
)


def _coerce_number(value: Any) -> Optional[float]:
    """Return ``value`` as a float when it plausibly is a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text)
        except ValueError:
            return None
    return None


def match_twin_parameter(key: str) -> Optional[str]:
    """
    The pipeline parameter a configuration key controls, if any.

    The key is matched on its last dotted component and on the full dotted
    path, so ``dynamic_batching.batching_window_ms`` and ``batching_window_ms``
    both resolve to ``batching_window_ms``.
    """
    if not key:
        return None
    lowered = str(key).lower()
    components = [part for part in lowered.split(".") if part]
    candidates = [components[-1]] if components else []
    candidates.append(lowered)
    for parameter, needles in _TWIN_PARAMETER_NEEDLES:
        for candidate in candidates:
            for needle in needles:
                if needle in candidate:
                    return parameter
    return None


def _iter_config_files(workspace: Path) -> List[Path]:
    """Every configuration file in the workspace, in a stable order."""
    found: List[Path] = []
    for pattern in ("*.yaml", "*.yml", "*.json"):
        found.extend(workspace.rglob(pattern))
    return sorted(p for p in found if p.is_file())


def read_workspace_config(workspace: Path) -> Dict[str, Dict[str, Any]]:
    """
    Every configuration file in the workspace, flattened to dotted keys.

    Returns:
        Mapping of workspace-relative path -> flattened configuration.
    """
    workspace = Path(workspace)
    result: Dict[str, Dict[str, Any]] = {}
    for path in _iter_config_files(workspace):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix.lower() == ".json":
                data = json.loads(text)
            else:
                data = yaml.safe_load(text)
        except Exception as exc:
            logger.debug(f"Could not parse config {path}: {exc}")
            continue
        if not isinstance(data, dict):
            continue
        flat = _flatten(data)
        if flat:
            result[path.relative_to(workspace).as_posix()] = flat
    return result


def _flatten(data: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten a nested mapping into dotted keys."""
    flat: Dict[str, Any] = {}
    if not isinstance(data, dict):
        return flat
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{full}."))
        else:
            flat[full] = value
    return flat


def read_source_parameters(workspace: Path) -> Dict[str, float]:
    """
    Numeric assignments found in the workspace's source files.

    A configuration file is not the only place a pipeline knob lives: a ROS
    node may set its queue depth in ``__init__``.  Reading those assignments
    is what lets the regression test see a patch that changed source code.
    """
    workspace = Path(workspace)
    found: Dict[str, float] = {}
    for path in sorted(workspace.rglob("*.py")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for match in _SOURCE_ASSIGNMENT_RE.finditer(text):
            name = match.group("name")
            parameter = match_twin_parameter(name)
            if parameter is None:
                continue
            number = _coerce_number(match.group("value"))
            if number is None:
                continue
            found[parameter] = number
    return found


def parameters_from_workspace(
    base: Any, workspace: Path
) -> Dict[str, float]:
    """
    The pipeline parameters the workspace currently declares.

    The result is a set of *overrides* on the incident's calibrated model: the
    values the workspace's own configuration and source files declare.  A
    parameter the workspace does not mention is absent from the result, so the
    model's calibrated value survives untouched.

    Args:
        base: Either a :class:`SystemModel` (its calibrated parameters are
            used) or a plain mapping of current parameter values.
        workspace: The verification workspace to read.
    """
    workspace = Path(workspace)
    overrides: Dict[str, float] = {}

    if hasattr(base, "parameters"):
        current = dict(base.parameters.as_dict())
    elif isinstance(base, dict):
        current = dict(base)
    else:
        current = {}

    for flat in read_workspace_config(workspace).values():
        for key, value in flat.items():
            parameter = match_twin_parameter(key)
            if parameter is None:
                continue
            number = _coerce_number(value)
            if number is None:
                continue
            overrides[parameter] = number

    # Source-level assignments are a fallback: a configuration file wins over
    # a source default when both mention the same knob.
    for parameter, number in read_source_parameters(workspace).items():
        overrides.setdefault(parameter, number)

    # Only report what actually differs from the calibrated model, so the
    # override set is an honest description of the patch.
    changed: Dict[str, float] = {}
    for parameter, number in overrides.items():
        baseline = current.get(parameter)
        if baseline is None:
            changed[parameter] = number
            continue
        try:
            if abs(float(baseline) - number) > 1e-9:
                changed[parameter] = number
        except (TypeError, ValueError):
            changed[parameter] = number
    return changed


def is_safety_enable_key(key: str) -> bool:
    """Whether a configuration key arms a safety behaviour."""
    lowered = str(key).lower()
    return any(needle in lowered for needle in _SAFETY_ENABLE_NEEDLES)


def is_safety_limit_key(key: str) -> bool:
    """Whether a configuration key expresses a safety limit."""
    lowered = str(key).lower()
    return any(needle in lowered for needle in _SAFETY_LIMIT_NEEDLES)


def safety_snapshot(workspace: Path) -> Dict[str, Any]:
    """
    Every safety-relevant value the workspace declares.

    Returns:
        Mapping of dotted key -> value, for the keys that either arm a safety
        behaviour or express a safety limit.
    """
    snapshot: Dict[str, Any] = {}
    for rel, flat in read_workspace_config(Path(workspace)).items():
        for key, value in flat.items():
            if is_safety_enable_key(key) or is_safety_limit_key(key):
                snapshot[f"{rel}::{key}"] = value
    return snapshot


def compare_safety(
    original: Dict[str, Any], patched: Dict[str, Any]
) -> List[str]:
    """
    The ways a patch weakened a safety declaration.

    Two rules are enforced:

    * an ``enable`` flag that was true must still be true;
    * a numeric ``limit`` must not have been raised.

    A value that vanished counts as a weakening too: removing the declaration
    of a limit is the same as removing the limit.
    """
    violations: List[str] = []
    for key, before in original.items():
        if key not in patched:
            violations.append(f"safety declaration removed: {key} (was {before!r})")
            continue
        after = patched[key]
        leaf = key.split("::")[-1]
        if is_safety_enable_key(leaf):
            if before is True and after is not True:
                violations.append(
                    f"safety behaviour disabled: {key} ({before!r} -> {after!r})"
                )
        elif is_safety_limit_key(leaf):
            before_number = _coerce_number(before)
            after_number = _coerce_number(after)
            if before_number is not None and after_number is not None:
                if after_number > before_number:
                    violations.append(
                        f"safety limit raised: {key} ({before_number:g} -> {after_number:g})"
                    )
    return violations

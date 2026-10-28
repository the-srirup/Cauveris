"""
Shared hypothesis -> intervention mapping.

Maps a hypothesis onto the concrete knobs of the digital twin, so the sandbox,
the simulation, the patch forge and the verifier all agree on what an
experiment actually changes.

Two sources are used, in order of trust:

1. **The structured proposal.**  The hypothesis layer knows exactly which
   parameter it wants changed and to what value, and says so in
   ``proposed_changes``.  Nothing has to be guessed from prose.
2. **The intervention text.**  A hypothesis produced by a language model has
   no structured proposal, so its text is parsed.  The parser is a fallback,
   not the primary path.

Every knob the twin understands is named after the twin's parameter set, so a
change that reaches the twin is the same change that reaches the config file.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cauveris.analysis.parameter_registry import PATCHABLE_PARAMETERS

logger = logging.getLogger(__name__)

#: The parameters an intervention may set.  Anything else is ignored: a
#: proposal that names a knob the twin cannot be asked to change cannot be
#: tested.
#:
#: This is the *configurable* set, not the simulatable one.  The twin models
#: a measured quantity as well as a knob - the working set a workload needed
#: (``resource_demand_mb``) is a fact about the incident and not something a
#: patch can set.  Letting an intervention assign it would let a patch
#: "fix" an incident by rewriting the measurement of it.
#:
#: Derived from :mod:`cauveris.analysis.parameter_registry`.  The registry is
#: the single source of truth: a parameter it lists as configurable can be
#: simulated, patched and verified, and a parameter it does not list can do
#: none of those.  The list used to be written out here by hand, which meant
#: a new failure family could not be fixed until this tuple was edited - and
#: until three other lists elsewhere were edited to match.
TWIN_PARAMETERS = PATCHABLE_PARAMETERS


@dataclass
class InterventionPlan:
    """Concrete configuration change derived from a hypothesis."""

    #: Parameter overrides to apply to the twin's parameter set.
    parameter_overrides: Dict[str, float] = field(default_factory=dict)
    # Human-readable description of applied changes (used for sandbox logs)
    applied_changes: Dict[str, str] = field(default_factory=dict)
    #: Files the change belongs in, so the sandbox and the patch forge know
    #: which real configuration file to edit.
    target_files: Dict[str, str] = field(default_factory=dict)
    #: Configuration keys to change, per parameter.
    target_keys: Dict[str, str] = field(default_factory=dict)
    #: Whether the change is expected to restore compliance by itself.
    sufficient_on_its_own: bool = True

    # -- convenience accessors used by the sandbox and the twin ---------------

    @property
    def batching_window_ms(self) -> Optional[float]:
        return self.parameter_overrides.get("batching_window_ms")

    @property
    def max_batch_size(self) -> Optional[int]:
        value = self.parameter_overrides.get("max_batch_size")
        return int(value) if value is not None else None

    @property
    def qos_queue_depth(self) -> Optional[int]:
        value = self.parameter_overrides.get("qos_queue_depth")
        return int(value) if value is not None else None

    @property
    def consumer_rate_hz(self) -> Optional[float]:
        return self.parameter_overrides.get("consumer_rate_hz")

    @property
    def transport_mean_ms(self) -> Optional[float]:
        return self.parameter_overrides.get("transport_mean_ms")

    @property
    def server_workers(self) -> Optional[int]:
        value = self.parameter_overrides.get("server_workers")
        return int(value) if value is not None else None

    @property
    def clock_skew_ms(self) -> Optional[float]:
        return self.parameter_overrides.get("clock_skew_ms")

    @property
    def db_pool_size(self) -> Optional[float]:
        return self.parameter_overrides.get("db_pool_size")

    @property
    def gpu_contention_ms(self) -> Optional[float]:
        """Kept for compatibility: GPU contention is a modelled batch cost."""
        return self.parameter_overrides.get("gpu_contention_ms")

    @property
    def is_baseline(self) -> bool:
        return not self.applied_changes

    def as_dict(self) -> Dict[str, Any]:
        return {
            "parameter_overrides": dict(self.parameter_overrides),
            "applied_changes": dict(self.applied_changes),
            "target_files": dict(self.target_files),
            "target_keys": dict(self.target_keys),
            "sufficient_on_its_own": self.sufficient_on_its_own,
        }


def _text(*parts: Any) -> str:
    return " ".join(str(p) for p in parts if p).lower()


def _describe(plan: InterventionPlan, parameter: str, current: Any, target: Any) -> None:
    """Record a human-readable description of one applied change."""
    key = plan.target_keys.get(parameter, parameter)
    file = plan.target_files.get(parameter)
    label = f"{key}: {current} -> {target}" if current is not None else f"{key}: {target}"
    if file:
        plan.applied_changes[file] = label
    else:
        plan.applied_changes[parameter] = label


def _plan_from_proposed_changes(
    plan: InterventionPlan, proposed: List[Dict[str, Any]]
) -> bool:
    """
    Apply the hypothesis's structured proposal.

    Returns whether anything was applied.  A proposal naming a parameter the
    twin does not model is skipped rather than guessed at.
    """
    applied = False
    for change in proposed or []:
        if not isinstance(change, dict):
            continue
        parameter = str(change.get("parameter") or "").strip()
        target = change.get("target_value")
        if parameter not in TWIN_PARAMETERS or target is None:
            continue
        try:
            target_value = float(target)
        except (TypeError, ValueError):
            continue
        current = change.get("current_value")
        plan.parameter_overrides[parameter] = target_value
        if change.get("file"):
            plan.target_files[parameter] = str(change["file"])
        if change.get("config_key"):
            plan.target_keys[parameter] = str(change["config_key"])
        if not plan.sufficient_on_its_own:
            pass
        elif not change.get("sufficient_on_its_own", True):
            plan.sufficient_on_its_own = False
        _describe(plan, parameter, current, target_value)
        applied = True
    return applied


def _plan_from_text(plan: InterventionPlan, text: str) -> bool:
    """Fall back to parsing an intervention that has no structured proposal."""
    params = text

    # Extract target file if mentioned, e.g. "in config/inference.yaml"
    file_match = re.search(r"\b(?:in\s+)?([a-zA-Z0-9_\-\./]+\.(?:yaml|yml|json|py|cfg|ini|toml))\b", text, re.IGNORECASE)
    detected_file = file_match.group(1) if file_match else None

    # Check for "from X to Y" patterns to record baseline value
    from_match = re.search(r"from\s*(\d+(?:\.\d+)?)\s*(?:ms|hz)?\s*to", text, re.IGNORECASE)
    from_val = float(from_match.group(1)) if from_match else None

    if "batching_window" in text or "batching window" in text:
        new_window = _extract_number(
            params, r"batching[._ ]*window[._ ]*ms\s*(?:to|=|:)?\s*(\d+(?:\.\d+)?)"
        )
        if new_window is None:
            new_window = _extract_number(
                params, r"(?:reduce|lower|set|decrease)[^.\n]*?to\s*(\d+(?:\.\d+)?)\s*ms"
            )
        if new_window is not None:
            plan.parameter_overrides["batching_window_ms"] = new_window
            # No file is guessed: the golden incident's file names are
            # meaningless for another incident, and a wrong preference is
            # worse than none - the patch forge searches the real bundle
            # for the key either way.
            target_f = detected_file
            if target_f:
                plan.target_files["batching_window_ms"] = target_f
            plan.target_keys["batching_window_ms"] = "batching_window_ms"
            current_w = from_val if from_val is not None else 200
            _describe(plan, "batching_window_ms", int(current_w) if int(current_w) == current_w else current_w, int(new_window) if int(new_window) == new_window else new_window)
            return True

    if "qos" in text or "queue depth" in text or "queue_depth" in text:
        depth = _extract_number(params, r"depth\s*(?:to|=|:)\s*(\d+)")
        if depth is None:
            depth = 1
        plan.parameter_overrides["qos_queue_depth"] = float(depth)
        target_f = detected_file
        if target_f:
            plan.target_files["qos_queue_depth"] = target_f
        plan.target_keys["qos_queue_depth"] = "qos_depth"
        _describe(plan, "qos_queue_depth", int(from_val) if from_val is not None else 10, int(depth))
        return True

    if "clock" in text or "skew" in text or "ntp" in text:
        if "tolerance" in text or "correct" in text or "sync" in text:
            plan.parameter_overrides["clock_skew_ms"] = 0.0
            target_f = detected_file
            if target_f:
                plan.target_files["clock_skew_ms"] = target_f
            plan.target_keys["clock_skew_ms"] = "max_clock_skew_tolerance_ms"
            _describe(plan, "clock_skew_ms", from_val, 0.0)
            return True

    if "rate" in text and "hz" in text:
        rate = _extract_number(params, r"rate\s*(?:to|=|:)?\s*(\d+(?:\.\d+)?)\s*hz")
        if rate is None:
            rate = _extract_number(params, r"to\s*(\d+(?:\.\d+)?)\s*hz")
        if rate is not None:
            plan.parameter_overrides["consumer_rate_hz"] = rate
            if detected_file:
                plan.target_files["consumer_rate_hz"] = detected_file
            _describe(plan, "consumer_rate_hz", from_val, rate)
            return True

    if "link latency" in text or "network latency" in text or "transport" in text:
        target = _extract_number(params, r"(?:below|under|to)\s*(\d+(?:\.\d+)?)\s*ms")
        if target is not None:
            plan.parameter_overrides["transport_mean_ms"] = target
            if detected_file:
                plan.target_files["transport_mean_ms"] = detected_file
            _describe(plan, "transport_mean_ms", from_val, target)
            return True

    if "worker" in text or "capacity" in text or "concurren" in text:
        workers = _extract_number(params, r"(\d+)\s*worker")
        if workers is None:
            workers = _extract_number(params, r"workers[^\d]{0,20}(\d+)")
        if workers is not None:
            plan.parameter_overrides["server_workers"] = float(workers)
            if detected_file:
                plan.target_files["server_workers"] = detected_file
            _describe(plan, "server_workers", int(from_val) if from_val is not None else None, int(workers))
            return True

    if "gpu" in text or "thermal" in text:
        size = _extract_number(params, r"batch\s*size\s*(?:to|=|:)\s*(\d+)")
        if size is None:
            size = _extract_number(params, r"max_batch[._ ]*size\s*(?:to|=|:)?\s*(\d+)")
        if size is not None:
            plan.parameter_overrides["max_batch_size"] = float(size)
            target_f = detected_file
            if target_f:
                plan.target_files["max_batch_size"] = target_f
            plan.target_keys["max_batch_size"] = "max_batch_size"
            _describe(plan, "max_batch_size", int(from_val) if from_val is not None else 8, int(size))
            return True

    return False


def map_hypothesis_to_intervention(
    hypothesis_id: str,
    intervention: Optional[str] = None,
    likely_parameters: Optional[list] = None,
    causal_claim: Optional[str] = None,
    proposed_changes: Optional[list] = None,
) -> InterventionPlan:
    """
    Derive an :class:`InterventionPlan` from a hypothesis.

    The structured proposal wins; the intervention text is the fallback for
    hypotheses that come from a language model.
    """
    plan = InterventionPlan()
    applied = _plan_from_proposed_changes(plan, proposed_changes or [])
    if not applied:
        text = _text(hypothesis_id, intervention, likely_parameters, causal_claim)
        _plan_from_text(plan, text)
    return plan


def map_experiment_to_intervention(
    hypothesis_id: str,
    intervention: Optional[str] = None,
    likely_parameters: Optional[list] = None,
    causal_claim: Optional[str] = None,
    proposed_changes: Optional[list] = None,
) -> InterventionPlan:
    """Convenience wrapper for Experiment objects stored in sandbox/simulation."""
    return map_hypothesis_to_intervention(
        hypothesis_id=hypothesis_id,
        intervention=intervention,
        likely_parameters=likely_parameters,
        causal_claim=causal_claim,
        proposed_changes=proposed_changes,
    )


def _extract_number(text: Optional[str], pattern: str) -> Optional[float]:
    """Extract the first integer/float captured group matching pattern."""
    if not text:
        return None
    m = re.search(pattern, str(text), re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, IndexError):
            return None
    return None

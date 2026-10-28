"""
Canonical Invariant Registry and Conflict Resolution Engine.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    AUTHORITY_PRIORITY,
    Invariant,
    InvariantAuthority,
    InvariantCandidate,
    InvariantConflict,
    InvariantKind,
    InvariantSet,
    InvariantSetStatus,
    InvariantStatus,
)
from .units import are_units_compatible, normalize_value

logger = logging.getLogger(__name__)

STANDARD_INVARIANTS = {
    "perception_freshness": {
        "name": "Perception freshness budget",
        "default_unit": "ms",
        "scope": "control_loop",
        "description": "Maximum age of perception frame delivered to control loop",
    },
    "control_deadline": {
        "name": "Control loop execution deadline",
        "default_unit": "ms",
        "scope": "control_loop",
        "description": "Maximum end-to-end latency for control command computation",
    },
    "request_timeout": {
        "name": "Request timeout",
        "default_unit": "ms",
        "scope": "service",
        "description": "Client-declared maximum waiting time for request response",
    },
    "dependency_timeout": {
        "name": "Dependency timeout",
        "default_unit": "ms",
        "scope": "dependency",
        "description": "Maximum time allowed for downstream dependency response",
    },
    "queue_capacity": {
        "name": "Queue capacity limit",
        "default_unit": "items",
        "scope": "queue",
        "description": "Maximum depth of ingress or QoS buffer before dropping",
    },
    "memory_limit": {
        "name": "Working set memory envelope",
        "default_unit": "MB",
        "scope": "process",
        "description": "Maximum memory before process termination (OOM kill)",
    },
    "cpu_limit": {
        "name": "CPU core quota",
        "default_unit": "cores",
        "scope": "process",
        "description": "CPU bandwidth limit allocated to process",
    },
    "gpu_memory_limit": {
        "name": "GPU memory allocation limit",
        "default_unit": "MB",
        "scope": "gpu",
        "description": "Maximum VRAM accessible before GPU allocation failure",
    },
    "max_accepted_loss": {
        "name": "Maximum accepted packet loss",
        "default_unit": "%",
        "scope": "network",
        "description": "Maximum acceptable network transport packet loss rate",
    },
    "max_accepted_jitter": {
        "name": "Maximum transport jitter",
        "default_unit": "ms",
        "scope": "network",
        "description": "Maximum acceptable variance in transport latency",
    },
    "worker_capacity": {
        "name": "Worker concurrency limit",
        "default_unit": "workers",
        "scope": "pool",
        "description": "Maximum parallel workers serving requests",
    },
    "max_lock_wait": {
        "name": "Maximum lock acquisition timeout",
        "default_unit": "ms",
        "scope": "concurrency",
        "description": "Maximum wait duration before contending lock acquisition times out",
    },
    "emergency_stop_requirement": {
        "name": "Emergency stop triggering requirement",
        "default_unit": "bool",
        "scope": "safety_watchdog",
        "description": "Mandatory safety watchdog trip when freshness or deadline fails",
    },
    "minimum_clearance": {
        "name": "Minimum dynamic obstacle clearance",
        "default_unit": "m",
        "scope": "kinematics",
        "description": "Minimum ground distance required between robot and obstacles",
    },
    "max_unsafe_exposure_ms": {
        "name": "Maximum unsafe exposure duration",
        "default_unit": "ms",
        "scope": "safety_watchdog",
        "description": "Maximum cumulative time permitted in an unverified or degraded state",
    },
}


class InvariantRegistry:
    """
    Authoritative builder and conflict resolver for incident invariant sets.
    """

    def __init__(self, incident_id: str):
        self.incident_id = incident_id
        self._candidates: Dict[str, List[InvariantCandidate]] = {}
        self._operator_resolutions: Dict[str, Dict[str, Any]] = {}

    def register_candidate(
        self,
        invariant_id: str,
        value: float,
        unit: str,
        authority: InvariantAuthority,
        source_artifact_id: Optional[str] = None,
        source_locator: Optional[str] = None,
        confidence: float = 1.0,
    ) -> None:
        """Register an observed, declared, or derived candidate value for an invariant."""
        norm_val, norm_unit = normalize_value(value, unit)
        cand = InvariantCandidate(
            value=norm_val,
            unit=norm_unit,
            source_artifact_id=source_artifact_id,
            source_locator=source_locator,
            authority=authority,
            confidence=confidence,
        )
        if invariant_id not in self._candidates:
            self._candidates[invariant_id] = []
        self._candidates[invariant_id].append(cand)

    def apply_operator_resolution(
        self,
        invariant_id: str,
        selected_value: float,
        unit: str,
        audit_id: str,
        reason: str,
    ) -> None:
        """Persist an operator override resolving a conflicted invariant."""
        norm_val, norm_unit = normalize_value(selected_value, unit)
        self._operator_resolutions[invariant_id] = {
            "value": norm_val,
            "unit": norm_unit,
            "audit_id": audit_id,
            "reason": reason,
        }

    def build_invariant_set(self, version: str = "1.0.0") -> InvariantSet:
        """
        Builds the canonical InvariantSet according to authority policy.
        Silently merging conflicting values is strictly prohibited.
        """
        invariants: Dict[str, Invariant] = {}
        conflicts: List[InvariantConflict] = []
        has_blocking_conflict = False

        for inv_id, cands in self._candidates.items():
            meta = STANDARD_INVARIANTS.get(
                inv_id,
                {
                    "name": inv_id.replace("_", " ").capitalize(),
                    "default_unit": cands[0].unit if cands else "units",
                    "scope": "system",
                    "description": "",
                },
            )

            # Check unit compatibility across all candidates
            base_unit = cands[0].unit
            for c in cands[1:]:
                if not are_units_compatible(base_unit, c.unit):
                    # Incompatible physical dimensions cannot be unified
                    conflict = InvariantConflict(
                        invariant_id=inv_id,
                        status="CONFLICTED",
                        candidates=cands,
                        selected=None,
                        verification_blocked=True,
                        resolution_reason=f"Incompatible physical units: {base_unit} vs {c.unit}",
                    )
                    conflicts.append(conflict)
                    has_blocking_conflict = True
                    invariants[inv_id] = Invariant(
                        invariant_id=inv_id,
                        name=meta["name"],
                        value=None,
                        unit=base_unit,
                        status=InvariantStatus.CONFLICTED,
                        scope=meta["scope"],
                        limitations=[f"Conflicted due to incompatible units: {base_unit} vs {c.unit}"],
                    )
                    break
            else:
                # Group by normalized value
                distinct_values = set(c.value for c in cands)

                # Check operator resolution
                if inv_id in self._operator_resolutions:
                    op = self._operator_resolutions[inv_id]
                    invariants[inv_id] = Invariant(
                        invariant_id=inv_id,
                        name=meta["name"],
                        value=op["value"],
                        unit=op["unit"],
                        kind=InvariantKind.DECLARED,
                        authority=InvariantAuthority.OPERATOR_OVERRIDE,
                        priority=AUTHORITY_PRIORITY[InvariantAuthority.OPERATOR_OVERRIDE],
                        status=InvariantStatus.ACTIVE,
                        scope=meta["scope"],
                        assumptions=[f"Operator resolution {op['audit_id']}: {op['reason']}"],
                    )
                    continue

                if len(distinct_values) == 1:
                    # Consensus among all registered sources
                    best_cand = max(cands, key=lambda c: AUTHORITY_PRIORITY.get(c.authority, 0))
                    invariants[inv_id] = Invariant(
                        invariant_id=inv_id,
                        name=meta["name"],
                        value=best_cand.value,
                        unit=best_cand.unit,
                        kind=InvariantKind.DECLARED,
                        source_artifact_id=best_cand.source_artifact_id,
                        source_locator=best_cand.source_locator,
                        authority=best_cand.authority,
                        priority=AUTHORITY_PRIORITY.get(best_cand.authority, 50),
                        confidence=best_cand.confidence,
                        status=InvariantStatus.ACTIVE,
                        scope=meta["scope"],
                    )
                else:
                    # Values disagree. Check highest authority priority.
                    cands_sorted = sorted(
                        cands, key=lambda c: AUTHORITY_PRIORITY.get(c.authority, 0), reverse=True
                    )
                    highest_priority = AUTHORITY_PRIORITY.get(cands_sorted[0].authority, 0)
                    top_tier = [
                        c
                        for c in cands_sorted
                        if AUTHORITY_PRIORITY.get(c.authority, 0) == highest_priority
                    ]
                    top_values = set(c.value for c in top_tier)

                    if len(top_values) > 1:
                        # Direct conflict at the same authoritative priority level!
                        conflict = InvariantConflict(
                            invariant_id=inv_id,
                            status="CONFLICTED",
                            candidates=cands,
                            selected=None,
                            verification_blocked=True,
                            resolution_reason=f"Conflicting values at authority tier {cands_sorted[0].authority.value}: {top_values}",
                        )
                        conflicts.append(conflict)
                        has_blocking_conflict = True
                        invariants[inv_id] = Invariant(
                            invariant_id=inv_id,
                            name=meta["name"],
                            value=None,
                            unit=base_unit,
                            status=InvariantStatus.CONFLICTED,
                            scope=meta["scope"],
                            limitations=[f"Conflicting authoritative values: {top_values}"],
                        )
                    else:
                        # Authoritative higher priority strictly overrides lower priority
                        winning_cand = top_tier[0]
                        invariants[inv_id] = Invariant(
                            invariant_id=inv_id,
                            name=meta["name"],
                            value=winning_cand.value,
                            unit=winning_cand.unit,
                            kind=InvariantKind.DECLARED,
                            source_artifact_id=winning_cand.source_artifact_id,
                            source_locator=winning_cand.source_locator,
                            authority=winning_cand.authority,
                            priority=highest_priority,
                            confidence=winning_cand.confidence,
                            status=InvariantStatus.ACTIVE,
                            scope=meta["scope"],
                            assumptions=[
                                f"Higher authority {winning_cand.authority.value} took precedence over lower tier sources"
                            ],
                        )

        # Generate deterministic invariant set ID
        content_hash = hashlib.sha256(
            json.dumps(
                {
                    "incident": self.incident_id,
                    "invariants": {k: v.model_dump() for k, v in invariants.items()},
                    "conflicts": [c.model_dump() for c in conflicts],
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:16]

        inv_set_id = f"invset_{self.incident_id}_{content_hash}"
        status = InvariantSetStatus.CONFLICTED if has_blocking_conflict else InvariantSetStatus.VALID

        return InvariantSet(
            invariant_set_id=inv_set_id,
            incident_id=self.incident_id,
            version=version,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            invariants=invariants,
            conflicts=conflicts,
            status=status,
        )

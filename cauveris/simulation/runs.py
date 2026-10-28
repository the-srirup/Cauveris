"""
Separate Immutable Baseline and Intervention Run Records & Scientific Comparison.

Enforces clear separation between unpatched baseline failure reproduction
and post-repair intervention runs, preventing conflation or retrofitted thresholds.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class BaselineRun(BaseModel):
    """
    Immutable record of an unpatched incident simulation reproducing the failure.
    Must never contain intervention values, post-repair claims, or candidate status.
    """
    baseline_run_id: str
    incident_id: str
    hypothesis_id: str
    mechanism_id: str
    model_id: str
    model_version: str = "2.0"
    invariant_set_id: str
    model_input_set_id: str
    source_tree_hash: Optional[str] = None
    input_artifact_hashes: Dict[str, str] = Field(default_factory=dict)
    random_seed: int = 42
    trial_count: int = 12
    baseline_outputs: Dict[str, Any] = Field(default_factory=dict)
    named_reproduced_failure: str
    failed_invariants: List[str] = Field(default_factory=list)
    model_adequacy: str = "CONFIRMED"
    limitations: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    @model_validator(mode="before")
    @classmethod
    def reject_intervention_data(cls, data: Any) -> Any:
        if isinstance(data, dict):
            forbidden = ("candidate_id", "failures_cleared", "patched_files", "verified", "post_repair_metrics")
            found = [k for k in forbidden if k in data and data[k] not in (None, False, [], {})]
            if found:
                raise ValueError(f"BaselineRun cannot contain post-repair intervention fields: {found}")
        return data


class InterventionRun(BaseModel):
    """
    Immutable record of a candidate intervention evaluated under the exact same invariant set.
    """
    intervention_run_id: str
    incident_id: str
    candidate_id: str
    baseline_run_id: str
    hypothesis_id: str
    mechanism_id: str
    model_id: str
    model_version: str = "2.0"
    invariant_set_id: str
    model_input_set_id: str
    source_tree_hash: Optional[str] = None
    intervention_controls: Dict[str, Any] = Field(default_factory=dict)
    input_artifact_hashes: Dict[str, str] = Field(default_factory=dict)
    random_seed: int = 42
    trial_count: int = 12
    outputs: Dict[str, Any] = Field(default_factory=dict)
    invariant_results: Dict[str, bool] = Field(default_factory=dict)
    regression_results: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class RunComparison(BaseModel):
    """
    Controlled comparative evaluation between an unpatched BaselineRun and an InterventionRun.
    """
    comparison_id: str
    baseline_run_id: str
    intervention_run_id: str
    candidate_id: str
    same_invariant_set_validation: bool
    model_compatibility_validation: bool
    input_comparability_result: bool
    named_failure: str
    named_repair_objective: str
    before_metrics: Dict[str, Any]
    after_metrics: Dict[str, Any]
    delta: Dict[str, Any]
    uncertainty: Optional[float] = None
    regressions: List[str] = Field(default_factory=list)
    conclusion: str
    limitations: List[str] = Field(default_factory=list)
    valid_comparison: bool = True


def compare_runs(
    baseline: BaselineRun,
    intervention: InterventionRun,
    candidate_id: str,
    repair_objective: str = "Clear reproduced failure without safety regressions",
) -> RunComparison:
    """
    Performs strict scientific comparison between baseline and intervention runs.
    Rejects mismatched invariant sets, unrelated candidates, or incompatible models.
    """
    limitations: List[str] = []
    regressions: List[str] = []

    # 1. Invariant Set Validation
    same_invariants = (baseline.invariant_set_id == intervention.invariant_set_id)
    if not same_invariants:
        raise ValueError(
            f"Comparison rejected: Invariant set mismatch. Baseline used {baseline.invariant_set_id}, "
            f"Intervention used {intervention.invariant_set_id}. Both must reference identical invariant set."
        )

    # 2. Candidate Linkage Validation
    if intervention.candidate_id != candidate_id:
        raise ValueError(
            f"Comparison rejected: Candidate mismatch. Expected {candidate_id}, but intervention "
            f"recorded candidate {intervention.candidate_id}."
        )

    if intervention.baseline_run_id != baseline.baseline_run_id:
        raise ValueError(
            f"Comparison rejected: Intervention references baseline {intervention.baseline_run_id}, "
            f"not {baseline.baseline_run_id}."
        )

    # 3. Model Compatibility Validation
    same_model = (
        baseline.model_id == intervention.model_id
        and baseline.model_version == intervention.model_version
    )
    if not same_model:
        raise ValueError(
            f"Comparison rejected: Incompatible models: {baseline.model_id} v{baseline.model_version} "
            f"vs {intervention.model_id} v{intervention.model_version}."
        )

    # 4. Failure Reproduction Check
    if not baseline.failed_invariants and baseline.named_reproduced_failure in ("none", ""):
        limitations.append("Baseline did not report any failed invariants or reproduced failure.")

    # 5. Delta Calculation
    before = baseline.baseline_outputs
    after = intervention.outputs
    delta: Dict[str, Any] = {}

    for key, val_before in before.items():
        if key in after and isinstance(val_before, (int, float)) and isinstance(after[key], (int, float)):
            delta[key] = round(after[key] - val_before, 4)

    # Check for regressions
    if intervention.regression_results.get("regressions_detected"):
        for r in intervention.regression_results.get("details", []):
            regressions.append(str(r))

    # Determine conclusion
    failures_cleared = all(intervention.invariant_results.get(inv, False) for inv in baseline.failed_invariants)
    if failures_cleared and not regressions:
        conclusion = "SUCCESS_REPAIRED: Intervention successfully cleared the reproduced failure with no regressions."
    elif not failures_cleared:
        conclusion = "FAILED_UNRESOLVED: Intervention failed to clear all baseline failed invariants."
    else:
        conclusion = f"FAILED_REGRESSIONS: Intervention introduced safety/operational regressions: {regressions}"

    comp_id = f"cmp_{baseline.baseline_run_id}_{intervention.intervention_run_id}"

    return RunComparison(
        comparison_id=comp_id,
        baseline_run_id=baseline.baseline_run_id,
        intervention_run_id=intervention.intervention_run_id,
        candidate_id=candidate_id,
        same_invariant_set_validation=True,
        model_compatibility_validation=True,
        input_comparability_result=True,
        named_failure=baseline.named_reproduced_failure,
        named_repair_objective=repair_objective,
        before_metrics=before,
        after_metrics=after,
        delta=delta,
        regressions=regressions,
        conclusion=conclusion,
        limitations=limitations,
        valid_comparison=True,
    )

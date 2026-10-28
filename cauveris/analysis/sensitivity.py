"""
Bounded sensitivity analysis for model verification.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple
import numpy as np

from .model_inputs import (
    ModelInputKind,
    ModelInputSet,
    SensitivityAnalysisReport,
    SensitivityLevel,
    SensitivityTrial,
    DEFAULT_PARAMETER_POLICIES,
)

logger = logging.getLogger(__name__)


def run_bounded_sensitivity_analysis(
    input_set: ModelInputSet,
    evaluate_intervention_fn: Callable[[Dict[str, float]], Tuple[bool, float]],
    target_param_ids: Optional[List[str]] = None,
) -> Dict[str, SensitivityAnalysisReport]:
    """
    Evaluates whether the repair remains robust across credible ranges of
    unsupported, assumed, or defaulted parameters.

    evaluate_intervention_fn: takes param overrides dict -> returns (repaired: bool, metric_value: float)
    """
    reports: Dict[str, SensitivityAnalysisReport] = {}

    # Determine parameters requiring sensitivity analysis
    if target_param_ids is None:
        target_param_ids = [
            pid for pid, inp in input_set.inputs.items()
            if inp.sensitivity in (SensitivityLevel.MEDIUM, SensitivityLevel.HIGH, SensitivityLevel.CRITICAL)
            and inp.kind in (ModelInputKind.EXPLICIT_DEFAULT, ModelInputKind.INFERRED)
        ]

    base_overrides = {
        pid: inp.value for pid, inp in input_set.inputs.items()
        if inp.value is not None
    }

    for pid in target_param_ids:
        policy = DEFAULT_PARAMETER_POLICIES.get(pid)
        if not policy:
            continue

        credible_range = policy.get("credible_range")
        if not credible_range:
            continue

        low, high = credible_range
        test_points = [low, (low + high) / 2.0, high]
        trials: List[SensitivityTrial] = []
        metrics: List[float] = []
        reversals = 0

        for pt in test_points:
            test_overrides = dict(base_overrides)
            test_overrides[pid] = pt
            repaired, metric = evaluate_intervention_fn(test_overrides)
            trials.append(
                SensitivityTrial(
                    parameter_id=pid,
                    test_value=pt,
                    unit=policy.get("unit", "units"),
                    repaired=repaired,
                    metric_value=round(metric, 3),
                )
            )
            metrics.append(metric)
            if not repaired:
                reversals += 1

        variance = float(np.var(metrics)) if len(metrics) > 1 else 0.0
        has_reversal = reversals > 0
        sens_level = policy.get("sensitivity", SensitivityLevel.MEDIUM)

        # If critical unknown/default input reverses repair success -> BLOCK verification
        blocks_verification = has_reversal and sens_level == SensitivityLevel.CRITICAL
        confidence_penalty = 0.4 if has_reversal else (0.1 if variance > 10.0 else 0.0)

        notes = []
        if has_reversal:
            notes.append(f"Repair outcome is unstable: failed {reversals}/{len(test_points)} test points across {credible_range}")
        if blocks_verification:
            notes.append("CRITICAL parameter uncertainty reverses conclusion. MODEL_VERIFIED blocked.")

        reports[pid] = SensitivityAnalysisReport(
            parameter_id=pid,
            sensitivity=sens_level,
            credible_range=credible_range,
            trials=trials,
            outcome_reversal_detected=has_reversal,
            outcome_variance=round(variance, 4),
            blocks_model_verification=blocks_verification,
            confidence_penalty=confidence_penalty,
            notes=notes,
        )

    return reports

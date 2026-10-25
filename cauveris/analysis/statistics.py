"""
Statistical primitives used by the analysis layer.

These are real estimators, not thresholds copied from a scenario:

* :func:`distribution` - robust location/scale statistics with percentiles.
* :func:`detect_change_point` - binary segmentation with a Welch statistic,
  used to find *when* behaviour changed rather than assuming a window.
* Welch t-test, Mann-Whitney U, Kolmogorov-Smirnov and Cohen's d for judging
  whether a before/after difference is real rather than noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:  # SciPy is a hard dependency of Cauveris but keep the import defensive.
    from scipy import stats as _scipy_stats
except Exception:  # pragma: no cover
    _scipy_stats = None  # type: ignore

__all__ = [
    "Distribution",
    "ChangePoint",
    "distribution",
    "percentile",
    "detect_change_point",
    "welch_t_test",
    "mann_whitney",
    "ks_two_sample",
    "cohens_d",
    "cliffs_delta",
    "linear_fit",
    "percentile_rank",
]


@dataclass
class Distribution:
    """Summary statistics of a sample."""

    count: int = 0
    mean: float = 0.0
    stdev: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    p50: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    median: float = 0.0
    mad: float = 0.0  # median absolute deviation

    def as_dict(self) -> Dict[str, float]:
        return {
            "count": self.count,
            "mean": round(self.mean, 4),
            "stdev": round(self.stdev, 4),
            "min": round(self.minimum, 4),
            "max": round(self.maximum, 4),
            "p50": round(self.p50, 4),
            "p90": round(self.p90, 4),
            "p95": round(self.p95, 4),
            "p99": round(self.p99, 4),
            "mad": round(self.mad, 4),
        }


@dataclass
class ChangePoint:
    """Result of change-point detection over a time-ordered series."""

    index: int
    t_statistic: float
    p_value: float
    effect_size: float
    before: Distribution = field(default_factory=Distribution)
    after: Distribution = field(default_factory=Distribution)
    before_values: List[float] = field(default_factory=list)
    after_values: List[float] = field(default_factory=list)
    alpha: float = 0.01

    @property
    def significant(self) -> bool:
        """
        Whether the change is credible.

        Two ways to qualify, because a short series (the common case in an
        incident bundle) can never reach a tiny p-value:

        * statistical: ``p < alpha`` and a non-trivial effect (``|d| > 0.2``);
        * practical: a large effect (``|d| >= 0.8``) with ``p < 0.05``.

        The second rule prevents a genuinely dramatic regime shift from being
        discarded merely because only a handful of samples exist.
        """
        effect = abs(self.effect_size)
        if self.p_value < self.alpha and effect > 0.2:
            return True
        return self.p_value < 0.05 and effect >= 0.8

    def as_dict(self) -> Dict[str, object]:
        return {
            "index": self.index,
            "t_statistic": round(self.t_statistic, 4),
            "p_value": float(f"{self.p_value:.6g}"),
            "effect_size": round(self.effect_size, 4),
            "significant": self.significant,
            "alpha": self.alpha,
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
        }


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (``q`` in [0, 100])."""
    if not len(values):
        return 0.0
    arr = np.asarray(values, dtype=float)
    return float(np.percentile(arr, q))


def distribution(values: Sequence[float]) -> Distribution:
    """Compute robust summary statistics of ``values``."""
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    if arr.size == 0:
        return Distribution()
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    return Distribution(
        count=int(arr.size),
        mean=float(arr.mean()),
        stdev=float(arr.std(ddof=1)) if arr.size > 1 else 0.0,
        minimum=float(arr.min()),
        maximum=float(arr.max()),
        p50=percentile(arr, 50),
        p90=percentile(arr, 90),
        p95=percentile(arr, 95),
        p99=percentile(arr, 99),
        median=median,
        mad=mad,
    )


def Welch_tTest(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float]:
    """Welch's unequal-variance t-test. Returns (t, p)."""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if arr_a.size < 2 or arr_b.size < 2:
        return 0.0, 1.0
    if _scipy_stats is not None:
        result = _scipy_stats.ttest_ind(arr_a, arr_b, equal_var=False)
        t = float(result.statistic)
        p = float(result.pvalue)
        if math.isnan(t):
            t = 0.0
        if math.isnan(p):
            p = 1.0
        return t, p
    # Fallback: normal approximation.
    mean_a, mean_b = arr_a.mean(), arr_b.mean()
    va = arr_a.var(ddof=1) / arr_a.size
    vb = arr_b.var(ddof=1) / arr_b.size
    denom = math.sqrt(va + vb)
    if denom == 0:
        return 0.0, 1.0
    t = (mean_a - mean_b) / denom
    return t, math.erfc(abs(t) / math.sqrt(2))


def welch_t_test(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float]:
    """Public alias for :func:`Welch_tTest`."""
    return Welch_tTest(a, b)


def mann_whitney(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float]:
    """Mann-Whitney U test (rank based, robust to non-normal data)."""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if arr_a.size < 2 or arr_b.size < 2:
        return 0.0, 1.0
    if _scipy_stats is not None:
        result = _scipy_stats.mannwhitneyu(arr_a, arr_b, alternative="two-sided")
        u = float(result.statistic)
        p = float(result.pvalue)
        if math.isnan(u):
            u = 0.0
        if math.isnan(p):
            p = 1.0
        return u, p
    # Fallback: rank-sum normal approximation.
    combined = np.concatenate([arr_a, arr_b])
    ranks = np.argsort(np.argsort(combined)) + 1.0
    rank_sum_a = ranks[: arr_a.size].sum()
    n1, n2 = arr_a.size, arr_b.size
    u = rank_sum_a - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)
    if sigma == 0:
        return u, 1.0
    z = (u - mu) / sigma
    return u, math.erfc(abs(z) / math.sqrt(2))


def ks_two_sample(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float]:
    """Two-sample Kolmogorov-Smirnov test. Returns (D, p)."""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if arr_a.size < 2 or arr_b.size < 2:
        return 0.0, 1.0
    if _scipy_stats is not None:
        result = _scipy_stats.ks_2samp(arr_a, arr_b)
        return float(result.statistic), float(result.pvalue)
    combined = np.sort(np.concatenate([arr_a, arr_b]))
    cdf_a = np.searchsorted(np.sort(arr_a), combined, side="right") / arr_a.size
    cdf_b = np.searchsorted(np.sort(arr_b), combined, side="right") / arr_b.size
    d = float(np.max(np.abs(cdf_a - cdf_b)))
    n_eff = arr_a.size * arr_b.size / (arr_a.size + arr_b.size)
    p = math.exp(-2.0 * n_eff * d * d) if d > 0 else 1.0
    return d, min(1.0, p)


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's d effect size (positive when ``a`` is larger than ``b``)."""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if arr_a.size < 2 or arr_b.size < 2:
        return 0.0
    pooled_var = (
        (arr_a.size - 1) * arr_a.var(ddof=1) + (arr_b.size - 1) * arr_b.var(ddof=1)
    ) / (arr_a.size + arr_b.size - 2)
    if pooled_var <= 0:
        return 0.0
    return float((arr_a.mean() - arr_b.mean()) / math.sqrt(pooled_var))


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Cliff's delta: a non-parametric effect size in [-1, 1]."""
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if arr_a.size == 0 or arr_b.size == 0:
        return 0.0
    greater = 0
    less = 0
    for x in arr_a:
        greater += int(np.sum(arr_b < x))
        less += int(np.sum(arr_b > x))
    total = arr_a.size * arr_b.size
    return float((greater - less) / total)


def detect_change_point(
    values: Sequence[float],
    *,
    min_segment: int = 3,
    max_depth: int = 3,
    alpha: float = 0.01,
) -> Optional[ChangePoint]:
    """
    Locate the most likely change point in a time-ordered numeric series.

    Binary segmentation: split the series at every admissible index, score each
    split with a Welch statistic, and recurse into the segment with the largest
    score. The reported change point is the split with the strongest evidence.

    Args:
        values: Time-ordered observations.
        min_segment: Minimum number of samples each side of a split.
        max_depth: Maximum recursion depth.
        alpha: Significance threshold used by :attr:`ChangePoint.significant`.

    Returns:
        The strongest :class:`ChangePoint`, or None if the series is too short
        or shows no significant shift.
    """
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    if arr.size < 2 * min_segment:
        return None

    best: Optional[ChangePoint] = None

    def score_segment(segment: np.ndarray, offset: int) -> Optional[ChangePoint]:
        nonlocal best
        if segment.size < 2 * min_segment:
            return None
        local_best: Optional[ChangePoint] = None
        for split in range(min_segment, segment.size - min_segment + 1):
            before = segment[:split]
            after = segment[split:]
            t, p = Welch_tTest(before, after)
            effect = cohens_d(after, before)
            candidate = ChangePoint(
                index=offset + split,
                t_statistic=t,
                p_value=p,
                effect_size=effect,
                before=distribution(before.tolist()),
                after=distribution(after.tolist()),
                before_values=before.tolist(),
                after_values=after.tolist(),
            )
            if local_best is None or abs(candidate.t_statistic) > abs(local_best.t_statistic):
                local_best = candidate
        if local_best is not None and (
            best is None or abs(local_best.t_statistic) > abs(best.t_statistic)
        ):
            best = local_best
        return local_best

    def recurse(segment: np.ndarray, offset: int, depth: int) -> None:
        if depth >= max_depth:
            return
        local = score_segment(segment, offset)
        if local is None:
            return
        if not local.significant:
            return
        # Recurse into whichever side still has enough data and signal.
        left = segment[: local.index - offset]
        right = segment[local.index - offset :]
        if left.size >= 2 * min_segment:
            recurse(left, offset, depth + 1)
        if right.size >= 2 * min_segment:
            recurse(right, local.index, depth + 1)

    recurse(arr, 0, 0)
    if best is None:
        return None
    best.p_value = min(1.0, best.p_value)
    return best


def linear_fit(xs: Sequence[float], ys: Sequence[float]) -> Optional[Tuple[float, float, float]]:
    """
    Least-squares fit of ``y = intercept + slope * x``.

    Returns:
        (intercept, slope, r_squared) or None if the fit is undefined.
    """
    arr_x = np.asarray(xs, dtype=float)
    arr_y = np.asarray(ys, dtype=float)
    if arr_x.size < 2 or arr_x.size != arr_y.size:
        return None
    var_x = float(np.var(arr_x))
    if var_x == 0:
        return None
    slope = float(np.cov(arr_x, arr_y, ddof=0)[0, 1] / var_x)
    intercept = float(arr_y.mean() - slope * arr_x.mean())
    pred = intercept + slope * arr_x
    ss_res = float(np.sum((arr_y - pred) ** 2))
    ss_tot = float(np.sum((arr_y - arr_y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return intercept, slope, max(0.0, min(1.0, r2))


def percentile_rank(value: float, population: Sequence[float]) -> float:
    """Fraction of ``population`` at or below ``value`` (0..1)."""
    arr = np.asarray(population, dtype=float)
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr <= value))

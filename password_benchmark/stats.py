"""Small numeric helpers shared by the runner and the analysis."""

import math


def percentile(values: list[float], pct: float) -> float:
    """Linear percentile, matching pandas Series.quantile default interpolation."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if pct < 0 or pct > 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    weight = rank - low
    return float(ordered[low] * (1.0 - weight) + ordered[high] * weight)


def median(values: list[float]) -> float:
    return percentile(values, 50)


def meets_budget(p95_ms: float, throughput_per_second: float, budget_ms: float, throughput_min: float) -> bool:
    """A configuration meets a budget only when both the latency and throughput rules hold."""
    return p95_ms <= budget_ms and throughput_per_second >= throughput_min


def bootstrap_percentile_ci(
    values: list[float], pct: float, resamples: int, confidence: float, seed: int
) -> tuple[float, float]:
    """Percentile-bootstrap interval for one percentile of the sample.

    Verifications are resampled as if exchangeable. Repeats of the same password
    run in sequence, so slow drift during a configuration is not modeled.
    """
    import numpy as np

    data = np.asarray(values, dtype=float)
    if data.size == 0:
        raise ValueError("bootstrap requires at least one value")
    rng = np.random.default_rng(seed)
    estimates = np.empty(resamples)
    chunk = max(1, min(resamples, 2_000_000 // max(1, data.size)))
    for start in range(0, resamples, chunk):
        stop = min(resamples, start + chunk)
        indexes = rng.integers(0, data.size, size=(stop - start, data.size))
        estimates[start:stop] = np.percentile(data[indexes], pct, axis=1, method="linear")
    tail = (1.0 - confidence) / 2.0 * 100.0
    low, high = np.percentile(estimates, [tail, 100.0 - tail])
    return float(low), float(high)


def bootstrap_median_contrast_ci(
    first: list[float], second: list[float], resamples: int, confidence: float, seed: int, ratio: bool
) -> tuple[float, float]:
    """Interval for median(first) / median(second) when ratio is true, otherwise their difference."""
    import numpy as np

    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    if a.size == 0 or b.size == 0:
        raise ValueError("bootstrap requires two non-empty samples")
    rng = np.random.default_rng(seed)
    estimates = np.empty(resamples)
    chunk = max(1, min(resamples, 2_000_000 // max(a.size, b.size)))
    for start in range(0, resamples, chunk):
        stop = min(resamples, start + chunk)
        size = stop - start
        median_a = np.median(a[rng.integers(0, a.size, size=(size, a.size))], axis=1)
        median_b = np.median(b[rng.integers(0, b.size, size=(size, b.size))], axis=1)
        estimates[start:stop] = median_a / median_b if ratio else median_a - median_b
    tail = (1.0 - confidence) / 2.0 * 100.0
    low, high = np.percentile(estimates, [tail, 100.0 - tail])
    return float(low), float(high)


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm step-down adjusted p-values, returned in the input order."""
    order = sorted(range(len(p_values)), key=lambda index: p_values[index])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def cliffs_delta_from_u(u_first: float, n_first: int, n_second: int) -> float:
    """P(first > second) - P(first < second), from the Mann-Whitney U of the first sample."""
    return 2.0 * u_first / (n_first * n_second) - 1.0


def cliffs_magnitude(delta: float) -> str:
    """Romano et al. (2006) thresholds."""
    size = abs(delta)
    if size < 0.147:
        return "negligible"
    if size < 0.33:
        return "small"
    if size < 0.474:
        return "medium"
    return "large"


def mann_whitney(first: list[float], second: list[float]) -> dict:
    from scipy.stats import mannwhitneyu

    result = mannwhitneyu(first, second, alternative="two-sided")
    delta = cliffs_delta_from_u(float(result.statistic), len(first), len(second))
    return {"u": float(result.statistic), "p_value": float(result.pvalue), "cliffs_delta": delta}


def kruskal_wallis(groups: list[list[float]]) -> dict:
    from scipy.stats import kruskal

    result = kruskal(*groups)
    total = sum(len(group) for group in groups)
    # Epsilon-squared effect size for Kruskal-Wallis H.
    epsilon_squared = float(result.statistic) * (total + 1) / (total * total - 1)
    return {"h": float(result.statistic), "p_value": float(result.pvalue), "epsilon_squared": epsilon_squared}

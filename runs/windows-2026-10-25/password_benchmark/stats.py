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

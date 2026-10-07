"""Turn raw metric values into 0-100 scores. See docs/research/metric-weights.md §3.1."""

from __future__ import annotations

import math

# Expected engagement rate by follower count: (upper bound exclusive, rate).
# TikTok: Influencer Marketing Factory via Emplicit (2025). Instagram: iqfluence tier ranges (midpoints).
ENGAGEMENT_BENCHMARKS: dict[str, list[tuple[float, float]]] = {
    "tiktok": [(100_000, 0.075), (500_000, 0.051), (1_000_000, 0.0448), (5_000_000, 0.0376),
               (10_000_000, 0.033), (math.inf, 0.0288)],
    "instagram": [(10_000, 0.032), (100_000, 0.0155), (500_000, 0.010), (1_000_000, 0.0065),
                  (math.inf, 0.004)],
}


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def log_scale(x: float, lo: float, hi: float) -> float:
    """0 at `lo`, 100 at `hi`, logarithmic in between."""
    if x <= 0:
        return 0.0
    return _clamp(100 * (math.log10(x) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)))


def growth_score(g: float, full: float) -> float:
    """50 = flat, 100 = growth of `full` (or more), 0 = the symmetric decline."""
    if g <= -1:
        return 0.0
    return _clamp(50 + 50 * math.log1p(g) / math.log1p(full))


def expected_engagement(followers: float, platform: str) -> float:
    for upper, rate in ENGAGEMENT_BENCHMARKS[platform]:
        if followers < upper:
            return rate
    return ENGAGEMENT_BENCHMARKS[platform][-1][1]


def benchmark_score(rate: float, followers: float, platform: str) -> float:
    """50 when the rate matches the size-tier benchmark, ±25 per doubling/halving."""
    if rate <= 0:
        return 0.0
    return _clamp(50 + 25 * math.log2(rate / expected_engagement(followers, platform)))

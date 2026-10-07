"""Pure scoring: metrics + weights -> ScoreResult. See docs/research/metric-weights.md §3."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from artistscore.scoring.normalize import benchmark_score, growth_score, log_scale

DEFAULT_WEIGHTS_PATH = Path(__file__).with_name("weights.yaml")

TIERS = [(75, "Superstar / headliner"), (60, "Established"), (45, "Mid-level"), (30, "Developing"),
         (0, "Emerging")]

STREAMING_GROWTH_KEYS = ("spotify_monthly_listeners", "deezer_fans", "lastfm_listeners")
SOCIAL_GROWTH_KEYS = ("instagram_followers", "tiktok_followers", "youtube_subscribers")
MIN_GROWTH_DAYS = 14


@dataclass
class MetricScore:
    key: str
    label: str
    value: float
    score: float
    weight: float
    effective_weight: float = 0.0  # share of the total score
    contribution: float = 0.0  # points added to the total
    source: str | None = None


@dataclass
class PillarScore:
    key: str
    label: str
    weight: float
    score: float | None
    mode: str = "level"  # "level" pillars average into the score; "adjust" pillars shift it around 50
    effective_weight: float = 0.0
    metrics: list[MetricScore] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class ScoreResult:
    total: float | None
    tier: str
    coverage: float
    confidence: str
    pillars: dict[str, PillarScore]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_weights(path: str | Path | None = None) -> dict[str, Any]:
    with open(path or DEFAULT_WEIGHTS_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def default_weights() -> dict[str, Any]:
    return copy.deepcopy(load_weights())


def tier_for(total: float | None) -> str:
    if total is None:
        return "Unscored"
    for cutoff, label in TIERS:
        if total >= cutoff:
            return label
    return TIERS[-1][1]


def confidence_for(coverage: float) -> str:
    return "high" if coverage >= 0.70 else "medium" if coverage >= 0.40 else "low"


def metric_score(key: str, spec: dict[str, Any], metrics: dict[str, float]) -> float:
    value = metrics[key]
    scale = spec.get("scale", "log")
    if scale == "log":
        return log_scale(value, float(spec["lo"]), float(spec["hi"]))
    if scale == "growth":
        return growth_score(value, float(spec["full"]))
    if scale == "benchmark":
        followers = metrics.get(spec.get("followers_metric", ""), 0.0)
        return benchmark_score(value, followers, spec["platform"])
    raise ValueError(f"unknown scale {scale!r} for {key}")


def score(metrics: dict[str, float], weights: dict[str, Any],
          sources: dict[str, str] | None = None) -> ScoreResult:
    sources = sources or {}
    pillars_cfg = weights["pillars"]
    total_pillar_weight = sum(max(0.0, float(p["weight"])) for p in pillars_cfg.values())

    pillars: dict[str, PillarScore] = {}
    coverage = 0.0
    for pkey, pcfg in pillars_cfg.items():
        pweight = max(0.0, float(pcfg["weight"]))
        metric_cfg = pcfg["metrics"]
        total_metric_weight = sum(max(0.0, float(m["weight"])) for m in metric_cfg.values())
        scored: list[MetricScore] = []
        missing: list[str] = []
        for mkey, mcfg in metric_cfg.items():
            mweight = max(0.0, float(mcfg["weight"]))
            if mkey not in metrics or metrics[mkey] is None:
                missing.append(mkey)
                continue
            scored.append(MetricScore(mkey, mcfg.get("label", mkey), float(metrics[mkey]),
                                      metric_score(mkey, mcfg, metrics), mweight, source=sources.get(mkey)))
            if total_pillar_weight and total_metric_weight:
                coverage += (pweight / total_pillar_weight) * (mweight / total_metric_weight)
        available_weight = sum(m.weight for m in scored)
        pillar_score = (sum(m.score * m.weight for m in scored) / available_weight) if available_weight else None
        pillars[pkey] = PillarScore(pkey, pcfg.get("label", pkey), pweight, pillar_score,
                                    pcfg.get("mode", "level"), metrics=scored, missing=missing)

    def spread(pillar: PillarScore, centre: float) -> None:
        metric_weight = sum(m.weight for m in pillar.metrics)
        for m in pillar.metrics:
            m.effective_weight = pillar.effective_weight * m.weight / metric_weight
            m.contribution = (m.score - centre) * m.effective_weight

    level = [p for p in pillars.values() if p.mode != "adjust" and p.score is not None and p.weight]
    level_weight = sum(p.weight for p in level)
    total = None
    if level_weight:
        total = 0.0
        for pillar in level:
            pillar.effective_weight = pillar.weight / level_weight
            total += pillar.score * pillar.effective_weight
            spread(pillar, 0.0)
        for pillar in pillars.values():
            if pillar.mode == "adjust" and pillar.score is not None and pillar.weight:
                pillar.effective_weight = pillar.weight / total_pillar_weight
                total += (pillar.score - 50) * pillar.effective_weight
                spread(pillar, 50.0)
        total = max(0.0, min(100.0, total))

    return ScoreResult(total, tier_for(total), coverage, confidence_for(coverage), pillars)


def _growth(cur: float | None, prev: float | None, days: float) -> float | None:
    if not cur or not prev or cur <= 0 or prev <= 0:
        return None
    return (cur / prev) ** (30.0 / days) - 1


def derive_momentum(history: list[dict[str, float]], timestamps: list[datetime]) -> dict[str, float]:
    """30-day growth of streaming and social audiences from the stored snapshot history.

    Compares the latest snapshot with the snapshot closest to 30 days before it, ignoring
    snapshots fewer than MIN_GROWTH_DAYS apart so short intervals cannot produce spikes.
    """
    if len(history) < 2:
        return {}
    latest, latest_ts = history[-1], timestamps[-1]
    candidates = [(abs((latest_ts - ts).total_seconds() / 86400 - 30), (latest_ts - ts).total_seconds() / 86400, snap)
                  for snap, ts in zip(history[:-1], timestamps[:-1])
                  if (latest_ts - ts).total_seconds() / 86400 >= MIN_GROWTH_DAYS]
    if not candidates:
        return {}
    _, days, reference = min(candidates, key=lambda c: c[0])

    result: dict[str, float] = {}
    for out_key, keys in (("streaming_growth_30d", STREAMING_GROWTH_KEYS), ("social_growth_30d", SOCIAL_GROWTH_KEYS)):
        rates = [g for k in keys if (g := _growth(latest.get(k), reference.get(k), days)) is not None]
        if rates:
            result[out_key] = mean(rates)
    return result

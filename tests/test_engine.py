from datetime import datetime, timedelta, timezone

import pytest

from artistscore.scoring.engine import derive_momentum, load_weights, score, tier_for

WEIGHTS = load_weights()

ALL_METRICS = {key: 1000.0 for pillar in WEIGHTS["pillars"].values() for key in pillar["metrics"]}


def test_default_pillar_weights_match_research():
    assert {k: p["weight"] for k, p in WEIGHTS["pillars"].items()} == {
        "live": 30, "reach": 25, "engagement": 20, "momentum": 15, "social": 10,
    }


def test_all_metrics_present_gives_full_coverage():
    result = score(ALL_METRICS, WEIGHTS)
    assert result.coverage == pytest.approx(1.0)
    assert result.confidence == "high"
    assert 0 <= result.total <= 100


def test_only_reach_metrics_renormalises_to_reach_pillar():
    reach = {k: 2_000_000.0 for k in WEIGHTS["pillars"]["reach"]["metrics"]}
    result = score(reach, WEIGHTS)
    assert result.total == pytest.approx(result.pillars["reach"].score)
    assert result.coverage == pytest.approx(0.25)
    assert result.confidence == "low"
    assert result.pillars["live"].score is None


def test_single_metric_contribution_and_effective_weight():
    result = score({"spotify_monthly_listeners": 50e6}, WEIGHTS)
    assert result.total == pytest.approx(100)
    metric = result.pillars["reach"].metrics[0]
    assert metric.key == "spotify_monthly_listeners"
    assert metric.effective_weight == pytest.approx(1.0)
    assert metric.contribution == pytest.approx(100)


def test_zero_pillar_weight_does_not_divide_by_zero():
    weights = load_weights()
    for pillar in weights["pillars"].values():
        pillar["weight"] = 0
    result = score({"spotify_monthly_listeners": 1e6}, weights)
    assert result.total is None
    assert result.tier == "Unscored"


def test_zero_metric_weights_in_pillar():
    weights = load_weights()
    for metric in weights["pillars"]["reach"]["metrics"].values():
        metric["weight"] = 0
    result = score({"spotify_monthly_listeners": 1e6, "instagram_followers": 1e6}, weights)
    assert result.pillars["reach"].score is None
    assert result.total == pytest.approx(result.pillars["social"].score)


def test_no_metrics_is_unscored():
    result = score({}, WEIGHTS)
    assert result.total is None and result.coverage == 0


def test_benchmark_metric_uses_follower_count():
    small = score({"tiktok_engagement_rate": 0.075, "tiktok_followers": 50_000}, WEIGHTS)
    big = score({"tiktok_engagement_rate": 0.075, "tiktok_followers": 20_000_000}, WEIGHTS)
    assert small.pillars["engagement"].score == pytest.approx(50)
    assert big.pillars["engagement"].score > 75


@pytest.mark.parametrize("total,tier", [(90, "Superstar / headliner"), (75, "Superstar / headliner"),
                                        (60, "Established"), (59.9, "Mid-level"), (45, "Mid-level"),
                                        (30, "Developing"), (10, "Emerging")])
def test_tier_boundaries(total, tier):
    assert tier_for(total) == tier


def _ts(days):
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days)


def test_momentum_requires_14_days():
    history = [{"spotify_monthly_listeners": 100.0}, {"spotify_monthly_listeners": 200.0}]
    assert derive_momentum(history, [_ts(0), _ts(10)]) == {}


def test_momentum_30_day_growth():
    history = [{"spotify_monthly_listeners": 100.0, "instagram_followers": 1000.0},
               {"spotify_monthly_listeners": 125.0, "instagram_followers": 1000.0}]
    result = derive_momentum(history, [_ts(0), _ts(30)])
    assert result["streaming_growth_30d"] == pytest.approx(0.25)
    assert result["social_growth_30d"] == pytest.approx(0.0)


def test_momentum_normalises_to_30_days_and_picks_closest_reference():
    history = [{"deezer_fans": 100.0}, {"deezer_fans": 110.0}, {"deezer_fans": 121.0}]
    # reference closest to 30 days before latest (day 60) is day 30 → 10% over 30 days
    result = derive_momentum(history, [_ts(0), _ts(30), _ts(60)])
    assert result["streaming_growth_30d"] == pytest.approx(0.10)


def test_momentum_skips_zero_baseline():
    history = [{"tiktok_followers": 0.0}, {"tiktok_followers": 500.0}]
    assert derive_momentum(history, [_ts(0), _ts(30)]) == {}


def test_flat_momentum_leaves_level_score_unchanged():
    level = {"spotify_monthly_listeners": 5e6}
    base = score(level, WEIGHTS).total
    assert score({**level, "streaming_growth_30d": 0.0}, WEIGHTS).total == pytest.approx(base)


def test_momentum_adjusts_by_at_most_half_its_weight():
    level = {"spotify_monthly_listeners": 5e6}
    base = score(level, WEIGHTS).total
    up = score({**level, "streaming_growth_30d": 1.0}, WEIGHTS)
    down = score({**level, "streaming_growth_30d": -0.9}, WEIGHTS)
    assert up.total == pytest.approx(base + 7.5)
    assert down.total == pytest.approx(base - 7.5)
    metric = up.pillars["momentum"].metrics[0]
    assert metric.contribution == pytest.approx(7.5)


def test_momentum_alone_is_unscored():
    result = score({"wikipedia_trend": 0.5}, WEIGHTS)
    assert result.total is None
    assert result.pillars["momentum"].score is not None


def test_adjusted_total_is_clamped():
    result = score({"spotify_monthly_listeners": 1e9, "streaming_growth_30d": 5.0}, WEIGHTS)
    assert result.total == 100

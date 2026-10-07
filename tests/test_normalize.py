import pytest

from artistscore.scoring.normalize import benchmark_score, growth_score, log_scale


def test_log_scale_anchors():
    assert log_scale(50e6, 1e3, 50e6) == 100
    assert log_scale(1e3, 1e3, 50e6) == 0
    assert round(log_scale(5e5, 1e3, 50e6)) == 57
    assert log_scale(1e9, 1e3, 50e6) == 100


@pytest.mark.parametrize("value", [0, -5])
def test_log_scale_non_positive_is_zero(value):
    assert log_scale(value, 1e3, 50e6) == 0


def test_growth_score():
    assert growth_score(0, 0.25) == 50
    assert growth_score(0.25, 0.25) == 100
    assert growth_score(1.0, 0.25) == 100
    assert growth_score(-0.2, 0.25) == 0  # ln(0.8) == -ln(1.25)
    assert growth_score(-1.0, 0.25) == 0


def test_benchmark_score_relative_to_size_tier():
    # 50K TikTok followers: expected 7.5%
    assert benchmark_score(0.075, 50_000, "tiktok") == pytest.approx(50)
    assert benchmark_score(0.30, 50_000, "tiktok") == pytest.approx(100)
    assert benchmark_score(0.075 / 4, 50_000, "tiktok") == pytest.approx(0)
    # 20M followers: expected 2.88%, so 2.88% is on par
    assert benchmark_score(0.0288, 20_000_000, "tiktok") == pytest.approx(50)
    assert benchmark_score(0.004, 5_000_000, "instagram") == pytest.approx(50)
    assert benchmark_score(0, 5_000_000, "instagram") == 0

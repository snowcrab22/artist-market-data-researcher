"""Jinja filters for presenting metric values."""

from __future__ import annotations

from datetime import datetime

from jinja2 import Environment

RATE_KEYS = ("_engagement_rate",)
GROWTH_KEYS = ("_growth_30d", "wikipedia_trend")
RATIO_KEYS = ("plays_per_listener", "follower_ratio", "festival_score", "spotify_popularity")


def compact(value: float | None) -> str:
    if value is None:
        return "—"
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            text = f"{value / limit:.1f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"


def metric_value(value: float | None, key: str) -> str:
    if value is None:
        return "—"
    if key.endswith(RATE_KEYS):
        return f"{value * 100:.2f}%"
    if key.endswith(GROWTH_KEYS):
        return f"{value * 100:+.1f}%"
    if key.endswith(RATIO_KEYS):
        return f"{value:,.2f}"
    return compact(value)


def score_text(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}"


def when(iso: str | None) -> str:
    if not iso:
        return "never"
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y %H:%M UTC")
    except ValueError:
        return iso


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def register(env: Environment) -> None:
    env.filters.update(compact=compact, metric_value=metric_value, score=score_text, when=when, pct=pct)
    env.globals["history_points"] = history_points


def history_points(history: list[dict], width: int = 640, height: int = 160, pad: int = 28) -> list[dict]:
    """Place scored snapshots on a fixed 0–100 y-axis for the inline SVG line chart."""
    scored = [h for h in history if h.get("total") is not None]
    if not scored:
        return []
    step = (width - 2 * pad) / max(1, len(scored) - 1)
    return [{"x": round(pad + i * step, 1), "y": round(height - pad - (h["total"] / 100) * (height - 2 * pad), 1),
             "total": h["total"], "label": when(h["fetched_at"])} for i, h in enumerate(scored)]



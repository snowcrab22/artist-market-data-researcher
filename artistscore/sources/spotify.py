"""Spotify public artist page: monthly listeners (not available in the Web API) and followers if embedded."""

from __future__ import annotations

import base64
import re

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext, SourceError, parse_count

NAME = "spotify"
LABEL = "Spotify (public artist page)"
REQUIRES: list[str] = []

JSON_LISTENERS = re.compile(r'"monthlyListeners"\s*:\s*(\d+)')
JSON_FOLLOWERS = [re.compile(r'"followers"\s*:\s*\{\s*"totalCount"\s*:\s*(\d+)'),
                  re.compile(r'"followers"\s*:\s*(\d+)')]
TEXT_LISTENERS = re.compile(r"(\d[\d,.\s  ]*[KMB]?)\s*monthly listeners", re.IGNORECASE)
TEXT_FOLLOWERS = re.compile(r"(\d[\d,.\s  ]*[KMB]?)\s*followers", re.IGNORECASE)
BASE64_SCRIPT = re.compile(r'<script[^>]*type="text/plain"[^>]*>([A-Za-z0-9+/=\s]{40,})</script>')


def _embedded_text(html: str) -> str:
    """Spotify sometimes ships page state as base64 in a text/plain script; decode it for searching."""
    decoded = []
    for blob in BASE64_SCRIPT.findall(html):
        try:
            decoded.append(base64.b64decode(blob).decode("utf-8", "ignore"))
        except ValueError:
            continue
    return "\n".join([html, *decoded])


def _best_text_count(pattern: re.Pattern[str], text: str) -> float | None:
    values = [(m.strip(), parse_count(m)) for m in pattern.findall(text)]
    values = [(raw, v) for raw, v in values if v]
    exact = [v for raw, v in values if not raw[-1:].isalpha()]
    return (exact or [v for _, v in values] or [None])[0]


def parse_page(html: str) -> tuple[float | None, float | None]:
    text = _embedded_text(html)
    listeners = float(m.group(1)) if (m := JSON_LISTENERS.search(text)) else _best_text_count(TEXT_LISTENERS, text)
    followers = None
    for pattern in JSON_FOLLOWERS:
        if m := pattern.search(text):
            followers = float(m.group(1))
            break
    if followers is None:
        followers = _best_text_count(TEXT_FOLLOWERS, text)
    return listeners, followers


async def fetch(ctx: SourceContext) -> SourceResult:
    if not ctx.links.spotify_id:
        return SourceResult.skipped(NAME, "no Spotify artist ID (add it under Links)")
    url = f"https://open.spotify.com/artist/{ctx.links.spotify_id}"
    response = await http.get(ctx.client, url, headers={"User-Agent": http.BROWSER_UA})
    listeners, followers = parse_page(response.text)
    if listeners is None and followers is None:
        raise SourceError("could not find monthly listeners on the Spotify page (layout changed or blocked)")
    metrics = []
    if listeners is not None:
        metrics.append(Metric("spotify_monthly_listeners", listeners, NAME))
    if followers is not None:
        metrics.append(Metric("spotify_followers", followers, NAME))
    return SourceResult.ok(NAME, metrics, {"url": url})

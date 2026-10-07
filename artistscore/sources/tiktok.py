"""TikTok public profile (best effort; TikTok often blocks automated requests): followers and engagement."""

from __future__ import annotations

import json
import re

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext, SourceError

NAME = "tiktok"
LABEL = "TikTok (public page, best effort)"
REQUIRES: list[str] = []
STATE = re.compile(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S)
FALLBACK = {k: re.compile(rf'"{k}"\s*:\s*(\d+)') for k in ("followerCount", "heartCount", "videoCount")}


def parse_stats(html: str) -> dict[str, float]:
    if match := STATE.search(html):
        state = json.loads(match.group(1))
        stats = state["__DEFAULT_SCOPE__"]["webapp.user-detail"]["userInfo"]["stats"]
        return {k: float(stats[k]) for k in ("followerCount", "heartCount", "videoCount") if k in stats}
    return {k: float(m.group(1)) for k, rx in FALLBACK.items() if (m := rx.search(html))}


async def fetch(ctx: SourceContext) -> SourceResult:
    handle = (ctx.links.tiktok or "").lstrip("@")
    if not handle:
        return SourceResult.skipped(NAME, "no TikTok handle linked")
    url = f"https://www.tiktok.com/@{handle}"
    response = await http.get(ctx.client, url, headers={"User-Agent": http.BROWSER_UA})
    stats = parse_stats(response.text)
    followers = stats.get("followerCount")
    if not followers:
        raise SourceError("TikTok did not return profile stats (blocked or changed); enter followers manually")
    metrics = [Metric("tiktok_followers", followers, NAME)]
    likes, videos = stats.get("heartCount"), stats.get("videoCount")
    if likes is not None:
        metrics.append(Metric("tiktok_likes", likes, NAME))
    if likes and videos:
        metrics.append(Metric("tiktok_engagement_rate", likes / videos / followers, NAME,
                              "lifetime average likes per video ÷ followers (approximation)"))
    return SourceResult.ok(NAME, metrics, {"url": url})

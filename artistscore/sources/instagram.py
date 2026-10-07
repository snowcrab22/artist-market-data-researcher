"""Instagram web profile endpoint (best effort; Instagram frequently requires login): followers, engagement."""

from __future__ import annotations

from statistics import mean

import httpx

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext, SourceError

NAME = "instagram"
LABEL = "Instagram (public profile, best effort)"
REQUIRES: list[str] = []
URL = "https://i.instagram.com/api/v1/users/web_profile_info/"
HEADERS = {"x-ig-app-id": "936619743392459", "User-Agent": http.BROWSER_UA}
BLOCKED = "Instagram refused anonymous access; enter followers / engagement manually"


async def fetch(ctx: SourceContext) -> SourceResult:
    handle = (ctx.links.instagram or "").lstrip("@")
    if not handle:
        return SourceResult.skipped(NAME, "no Instagram handle linked")
    try:
        response = await http.get(ctx.client, URL, params={"username": handle}, headers=HEADERS)
        user = response.json()["data"]["user"]
    except httpx.HTTPStatusError as exc:
        raise SourceError(f"{BLOCKED} (HTTP {exc.response.status_code})") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise SourceError(BLOCKED) from exc
    if not user:
        raise SourceError(f"Instagram user @{handle} not found")
    followers = float(user["edge_followed_by"]["count"])
    metrics = [Metric("instagram_followers", followers, NAME)]
    posts = [e["node"] for e in user.get("edge_owner_to_timeline_media", {}).get("edges", [])][:12]
    interactions = [
        (p.get("edge_liked_by") or p.get("edge_media_preview_like") or {}).get("count", 0)
        + (p.get("edge_media_to_comment") or {}).get("count", 0)
        for p in posts
    ]
    if interactions and followers:
        metrics.append(Metric("instagram_engagement_rate", mean(interactions) / followers, NAME,
                              f"(likes + comments) ÷ followers, last {len(interactions)} posts"))
    return SourceResult.ok(NAME, metrics, {"url": f"https://www.instagram.com/{handle}/"})

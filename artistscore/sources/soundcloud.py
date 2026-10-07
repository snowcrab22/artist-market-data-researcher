"""SoundCloud public profile (best effort): followers."""

from __future__ import annotations

import re

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext, SourceError

NAME = "soundcloud"
LABEL = "SoundCloud (public page)"
REQUIRES: list[str] = []
FOLLOWERS = re.compile(r'"followers_count"\s*:\s*(\d+)')


async def fetch(ctx: SourceContext) -> SourceResult:
    if not ctx.links.soundcloud:
        return SourceResult.skipped(NAME, "no SoundCloud profile linked")
    url = f"https://soundcloud.com/{ctx.links.soundcloud}"
    response = await http.get(ctx.client, url, headers={"User-Agent": http.BROWSER_UA})
    match = FOLLOWERS.search(response.text)
    if not match:
        raise SourceError("follower count not found on the SoundCloud page")
    return SourceResult.ok(NAME, [Metric("soundcloud_followers", float(match.group(1)), NAME)], {"url": url})

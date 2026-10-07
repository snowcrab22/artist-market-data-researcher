"""Bandsintown API (app_id issued by Bandsintown on request): trackers and upcoming events."""

from __future__ import annotations

from urllib.parse import quote

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext

NAME = "bandsintown"
LABEL = "Bandsintown"
REQUIRES = ["BANDSINTOWN_APP_ID"]


async def fetch(ctx: SourceContext) -> SourceResult:
    app_id = ctx.settings.get("BANDSINTOWN_APP_ID")
    if not app_id:
        return SourceResult.skipped(NAME, "BANDSINTOWN_APP_ID not set")
    name = ctx.links.bandsintown_name or ctx.name
    response = await http.get(ctx.client, f"https://rest.bandsintown.com/artists/{quote(name, safe='')}",
                              params={"app_id": app_id})
    payload = response.json() if response.text.strip() else None
    if not isinstance(payload, dict) or "tracker_count" not in payload:
        return SourceResult.skipped(NAME, "artist not found on Bandsintown")
    metrics = [Metric("bandsintown_trackers", float(payload["tracker_count"]), NAME)]
    if "upcoming_event_count" in payload:
        metrics.append(Metric("upcoming_shows", float(payload["upcoming_event_count"]), NAME))
    return SourceResult.ok(NAME, metrics, {"url": payload.get("url")})

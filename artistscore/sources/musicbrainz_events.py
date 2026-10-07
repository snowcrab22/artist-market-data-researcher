"""MusicBrainz events (no key): festival appearances (event type "Festival") and concerts."""

from __future__ import annotations

from artistscore import http
from artistscore.festivals import TRAILING_YEAR, match_festival
from artistscore.models import FestivalAppearance, Metric, SourceResult
from artistscore.sources.base import SourceContext, months_ago, parse_partial_date

NAME = "musicbrainz_events"
LABEL = "MusicBrainz events"
REQUIRES: list[str] = []
API = "https://musicbrainz.org/ws/2/event"
MAX_PAGES = 3


def _role(event: dict, mbid: str) -> str | None:
    for rel in event.get("relations", []):
        if rel.get("artist", {}).get("id") == mbid and "headliner" in (rel.get("attributes") or []):
            return "headliner"
    return None


async def fetch(ctx: SourceContext) -> SourceResult:
    mbid = ctx.links.mbid
    if not mbid:
        return SourceResult.skipped(NAME, "no MusicBrainz ID")
    events: list[dict] = []
    for page in range(MAX_PAGES):
        payload = await http.get_json(ctx.client, API, params={
            "artist": mbid, "inc": "artist-rels", "limit": 100, "offset": page * 100, "fmt": "json"})
        events.extend(payload.get("events", []))
        if len(events) >= payload.get("event-count", 0) or not payload.get("events"):
            break

    since = months_ago(ctx.today, 24)
    festivals: list[FestivalAppearance] = []
    shows: list[dict] = []
    for event in events:
        when = parse_partial_date(event.get("life-span", {}).get("begin"))
        if when is None:
            continue
        name = event.get("name", "")
        match = match_festival(name)
        if match or event.get("type") == "Festival":
            fest_name, tier = match or (TRAILING_YEAR.sub("", name) or name, 3)
            festivals.append(FestivalAppearance(fest_name, tier, when, _role(event, mbid), NAME))
        if when <= ctx.today:
            shows.append({"date": when.isoformat(), "name": name, "type": event.get("type"), "source": NAME})

    shows.sort(key=lambda s: s["date"], reverse=True)
    recent = sum(1 for s in shows if s["date"] >= since.isoformat())
    metrics = [Metric("shows_24mo", float(recent), NAME, "events listed on MusicBrainz")] if recent else []
    return SourceResult.ok(NAME, metrics, {"festivals": [f.to_dict() for f in festivals], "shows": shows})

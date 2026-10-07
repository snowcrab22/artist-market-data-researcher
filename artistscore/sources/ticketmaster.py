"""Ticketmaster Discovery API (free key): upcoming events and festival bookings."""

from __future__ import annotations

from datetime import date

from artistscore import http
from artistscore.festivals import match_festival
from artistscore.models import FestivalAppearance, Metric, SourceResult
from artistscore.sources.base import SourceContext

NAME = "ticketmaster"
LABEL = "Ticketmaster"
REQUIRES = ["TICKETMASTER_API_KEY"]
API = "https://app.ticketmaster.com/discovery/v2"


async def fetch(ctx: SourceContext) -> SourceResult:
    key = ctx.settings.get("TICKETMASTER_API_KEY")
    if not key:
        return SourceResult.skipped(NAME, "TICKETMASTER_API_KEY not set")
    found = await http.get_json(ctx.client, f"{API}/attractions.json", params={
        "keyword": ctx.name, "classificationName": "music", "apikey": key})
    attractions = [a for a in found.get("_embedded", {}).get("attractions", [])
                   if a.get("name", "").casefold() == ctx.name.casefold()]
    if not attractions:
        return SourceResult.skipped(NAME, "no exact-name attraction on Ticketmaster")
    attraction = attractions[0]
    upcoming_total = float((attraction.get("upcomingEvents") or {}).get("_total", 0))

    events = await http.get_json(ctx.client, f"{API}/events.json", params={
        "attractionId": attraction["id"], "size": 100, "sort": "date,asc", "apikey": key})
    upcoming, festivals = [], []
    for event in events.get("_embedded", {}).get("events", []):
        local_date = event.get("dates", {}).get("start", {}).get("localDate")
        if not local_date:
            continue
        venue = (event.get("_embedded", {}).get("venues") or [{}])[0]
        row = {"date": local_date, "name": event.get("name", ""), "venue": venue.get("name", ""),
               "city": (venue.get("city") or {}).get("name", ""),
               "country": (venue.get("country") or {}).get("countryCode", ""), "source": NAME}
        upcoming.append(row)
        if match := match_festival(row["name"]):
            festivals.append(FestivalAppearance(match[0], match[1], date.fromisoformat(local_date), None, NAME))
    return SourceResult.ok(NAME, [Metric("upcoming_shows", upcoming_total, NAME)], {
        "upcoming": upcoming, "festivals": [f.to_dict() for f in festivals]})

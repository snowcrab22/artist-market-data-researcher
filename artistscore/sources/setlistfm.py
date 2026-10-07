"""setlist.fm API (free non-commercial key): show history, countries, festival sets."""

from __future__ import annotations

from datetime import datetime

import httpx

from artistscore import http
from artistscore.festivals import match_festival
from artistscore.models import FestivalAppearance, Metric, SourceResult
from artistscore.sources.base import SourceContext, months_ago

NAME = "setlistfm"
LABEL = "setlist.fm"
REQUIRES = ["SETLISTFM_API_KEY"]
API = "https://api.setlist.fm/rest/1.0/artist/{mbid}/setlists"
MAX_PAGES = 10


def _parse(setlist: dict) -> dict | None:
    try:
        when = datetime.strptime(setlist["eventDate"], "%d-%m-%Y").date()
    except (KeyError, ValueError):
        return None
    venue = setlist.get("venue", {})
    city = venue.get("city", {})
    return {"date": when, "venue": venue.get("name", ""), "city": city.get("name", ""),
            "country": city.get("country", {}).get("code", ""), "tour": (setlist.get("tour") or {}).get("name", ""),
            "url": setlist.get("url")}


async def fetch(ctx: SourceContext) -> SourceResult:
    key = ctx.settings.get("SETLISTFM_API_KEY")
    if not key:
        return SourceResult.skipped(NAME, "SETLISTFM_API_KEY not set")
    if not ctx.links.mbid:
        return SourceResult.skipped(NAME, "setlist.fm needs a MusicBrainz ID")
    since = months_ago(ctx.today, 24)
    headers = {"x-api-key": key, "Accept": "application/json"}
    shows: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        try:
            payload = await http.get_json(ctx.client, API.format(mbid=ctx.links.mbid), params={"p": page},
                                          headers=headers)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:  # setlist.fm answers 404 when there are no setlists
                break
            raise
        parsed = [s for s in map(_parse, payload.get("setlist", [])) if s]
        shows.extend(parsed)
        per_page = payload.get("itemsPerPage", 20) or 20
        if not parsed or parsed[-1]["date"] < since or page * per_page >= payload.get("total", 0):
            break

    past = [s for s in shows if s["date"] <= ctx.today]
    recent = [s for s in past if s["date"] >= since]
    festivals = []
    for show in shows:
        match = match_festival(show["venue"]) or match_festival(show["tour"], generic=False)
        if match:
            festivals.append(FestivalAppearance(match[0], match[1], show["date"], None, NAME).to_dict())
    metrics = [Metric("shows_24mo", float(len(recent)), NAME),
               Metric("countries_24mo", float(len({s["country"] for s in recent if s["country"]})), NAME)]
    return SourceResult.ok(NAME, metrics, {
        "festivals": festivals,
        "shows": [{**s, "date": s["date"].isoformat(), "source": NAME} for s in past[:100]],
    })



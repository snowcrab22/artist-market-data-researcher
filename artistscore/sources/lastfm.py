"""Last.fm API (free key): unique scrobbling listeners, total plays and plays per listener."""

from __future__ import annotations

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext, SourceError

NAME = "lastfm"
LABEL = "Last.fm"
REQUIRES = ["LASTFM_API_KEY"]
API = "https://ws.audioscrobbler.com/2.0/"


async def _getinfo(ctx: SourceContext, key: str, **query: str) -> dict:
    params = {"method": "artist.getinfo", "api_key": key, "format": "json", "autocorrect": "1", **query}
    return await http.get_json(ctx.client, API, params=params)


async def fetch(ctx: SourceContext) -> SourceResult:
    key = ctx.settings.get("LASTFM_API_KEY")
    if not key:
        return SourceResult.skipped(NAME, "LASTFM_API_KEY not set")
    payload: dict = {}
    if ctx.links.mbid:
        payload = await _getinfo(ctx, key, mbid=ctx.links.mbid)
    if "artist" not in payload:
        payload = await _getinfo(ctx, key, artist=ctx.links.lastfm_name or ctx.name)
    if "artist" not in payload:
        raise SourceError(f"Last.fm: {payload.get('message', 'artist not found')}")
    artist = payload["artist"]
    listeners = float(artist["stats"]["listeners"])
    plays = float(artist["stats"]["playcount"])
    metrics = [Metric("lastfm_listeners", listeners, NAME), Metric("lastfm_plays", plays, NAME)]
    if listeners > 0:
        metrics.append(Metric("lastfm_plays_per_listener", plays / listeners, NAME))
    return SourceResult.ok(NAME, metrics, {"url": artist.get("url")})

"""Spotify Web API (optional client credentials): artist ID lookup, plus followers/popularity when the
API still returns them (they were removed for Development-Mode apps in February 2026)."""

from __future__ import annotations

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext, SourceError

NAME = "spotify_api"
LABEL = "Spotify Web API (optional)"
REQUIRES = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]
API = "https://api.spotify.com/v1"


async def _token(ctx: SourceContext, client_id: str, secret: str) -> str:
    response = await ctx.client.post("https://accounts.spotify.com/api/token",
                                     data={"grant_type": "client_credentials"}, auth=(client_id, secret))
    response.raise_for_status()
    return response.json()["access_token"]


async def fetch(ctx: SourceContext) -> SourceResult:
    client_id, secret = ctx.settings.get("SPOTIFY_CLIENT_ID"), ctx.settings.get("SPOTIFY_CLIENT_SECRET")
    if not (client_id and secret):
        return SourceResult.skipped(NAME, "Spotify client ID/secret not set (optional)")
    headers = {"Authorization": f"Bearer {await _token(ctx, client_id, secret)}"}
    details: dict = {}
    spotify_id = ctx.links.spotify_id
    if not spotify_id:
        found = await http.get_json(ctx.client, f"{API}/search", params={"q": ctx.name, "type": "artist", "limit": 10},
                                    headers=headers)
        exact = [a for a in found.get("artists", {}).get("items", []) if a.get("name", "").casefold() == ctx.name.casefold()]
        if not exact:
            raise SourceError("no exact-name artist in Spotify search")
        spotify_id = exact[0]["id"]
        details["links"] = {"spotify_id": spotify_id}
    artist = await http.get_json(ctx.client, f"{API}/artists/{spotify_id}", headers=headers)
    metrics = []
    if isinstance(artist.get("followers"), dict) and artist["followers"].get("total") is not None:
        metrics.append(Metric("spotify_followers", float(artist["followers"]["total"]), NAME))
    if artist.get("popularity") is not None:
        metrics.append(Metric("spotify_popularity", float(artist["popularity"]), NAME))
    return SourceResult.ok(NAME, metrics, details)

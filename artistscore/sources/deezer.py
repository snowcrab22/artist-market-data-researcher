"""Deezer public API (no key): fan count."""

from __future__ import annotations

from artistscore import http
from artistscore.models import Metric, SourceResult
from artistscore.sources.base import SourceContext, SourceError

NAME = "deezer"
LABEL = "Deezer"
REQUIRES: list[str] = []
API = "https://api.deezer.com"


def _check(payload: dict) -> dict:
    if "error" in payload:
        raise SourceError(f"Deezer error: {payload['error'].get('message', payload['error'])}")
    return payload


async def fetch(ctx: SourceContext) -> SourceResult:
    deezer_id = ctx.links.deezer_id
    details: dict = {}
    if not deezer_id:
        found = _check(await http.get_json(ctx.client, f"{API}/search/artist", params={"q": ctx.name, "limit": 10}))
        exact = [a for a in found.get("data", []) if a.get("name", "").casefold() == ctx.name.casefold()]
        if not exact:
            return SourceResult.skipped(NAME, "no exact name match on Deezer (add the Deezer ID under Links)")
        deezer_id = str(max(exact, key=lambda a: a.get("nb_fan", 0))["id"])
        details["links"] = {"deezer_id": deezer_id}
    artist = _check(await http.get_json(ctx.client, f"{API}/artist/{deezer_id}"))
    return SourceResult.ok(NAME, [Metric("deezer_fans", float(artist["nb_fan"]), NAME)],
                           {**details, "deezer_id": str(deezer_id), "url": artist.get("link")})

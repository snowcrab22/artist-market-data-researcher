"""Fake sources for service and web tests."""

from datetime import date
from types import SimpleNamespace

from artistscore.models import FestivalAppearance, Metric, SourceResult


def fake_source(name, metrics=None, details=None, status="ok", error=None, raises=None):
    async def fetch(ctx):
        if raises:
            raise raises
        if status == "skipped":
            return SourceResult.skipped(name, error or "no key")
        if status == "error":
            return SourceResult.failed(name, error or "boom")
        return SourceResult.ok(name, [Metric(k, v, name) for k, v in (metrics or {}).items()], details or {})

    return SimpleNamespace(NAME=name, LABEL=name.title(), REQUIRES=[], fetch=fetch)


def festival(name, tier, when, role=None, source="x"):
    return FestivalAppearance(name, tier, when, role, source).to_dict()


DEFAULT_FAKES = [
    fake_source("spotify", {"spotify_monthly_listeners": 2_000_000, "spotify_followers": 500_000}),
    fake_source("setlistfm", {"shows_24mo": 40, "countries_24mo": 8},
                {"festivals": [festival("Coachella", 1, date(2026, 4, 12))],
                 "shows": [{"date": "2026-04-12", "venue": "Empire Polo Club", "city": "Indio", "country": "US"}]}),
    fake_source("musicbrainz_events", {"shows_24mo": 3},
                {"festivals": [festival("Coachella", 1, date(2026, 4, 19), "headliner"),
                               festival("Pitchfork Music Festival", 2, date(2025, 7, 20))]}),
    fake_source("youtube", status="error", error="HTTP 403"),
    fake_source("lastfm", status="skipped", error="LASTFM_API_KEY not set"),
    fake_source("deezer", {"deezer_fans": 100_000}, {"links": {"deezer_id": "399"}}),
]

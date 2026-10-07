"""Seed clearly-labelled synthetic artists so the UI can be explored without API keys or network access."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from artistscore.festivals import festival_score
from artistscore.models import ArtistLinks, FestivalAppearance, Metric
from artistscore.service import derive_metrics
from artistscore.storage import Store

DEMO_ARTISTS = {
    "Demo: Arena Headliner (synthetic)": {
        "spotify_monthly_listeners": 28_000_000, "spotify_followers": 9_500_000, "lastfm_listeners": 2_100_000,
        "lastfm_plays_per_listener": 48, "youtube_subscribers": 8_200_000, "youtube_views": 4_100_000_000,
        "youtube_engagement_rate": 0.031, "deezer_fans": 3_400_000, "wikipedia_monthly_views": 310_000,
        "wikipedia_trend": 0.12, "instagram_followers": 12_000_000, "instagram_engagement_rate": 0.009,
        "tiktok_followers": 6_500_000, "tiktok_engagement_rate": 0.05, "shows_24mo": 95, "countries_24mo": 24,
        "upcoming_shows": 38, "bandsintown_trackers": 2_900_000, "soundcloud_followers": 410_000,
        "_festivals": [("Glastonbury", 1, 120, "headliner"), ("Coachella", 1, 540, "headliner"),
                       ("Primavera Sound", 1, 480, None), ("Osheaga", 2, 430, None)],
        "_growth": 0.04,
    },
    "Demo: Mid-level Touring Band (synthetic)": {
        "spotify_monthly_listeners": 650_000, "spotify_followers": 240_000, "lastfm_listeners": 180_000,
        "lastfm_plays_per_listener": 34, "youtube_subscribers": 95_000, "youtube_views": 41_000_000,
        "youtube_engagement_rate": 0.042, "deezer_fans": 52_000, "wikipedia_monthly_views": 9_000,
        "wikipedia_trend": 0.05, "instagram_followers": 140_000, "instagram_engagement_rate": 0.018,
        "tiktok_followers": 60_000, "tiktok_engagement_rate": 0.06, "shows_24mo": 110, "countries_24mo": 14,
        "upcoming_shows": 22, "bandsintown_trackers": 160_000, "soundcloud_followers": 21_000,
        "_festivals": [("Pitchfork Music Festival", 2, 80, None), ("Best Kept Secret", 2, 130, None),
                       ("Riverside Fest", 3, 300, None)],
        "_growth": 0.02,
    },
    "Demo: Viral Newcomer (synthetic)": {
        "spotify_monthly_listeners": 3_200_000, "spotify_followers": 90_000, "lastfm_listeners": 60_000,
        "lastfm_plays_per_listener": 6, "youtube_subscribers": 40_000, "youtube_views": 9_000_000,
        "youtube_engagement_rate": 0.02, "deezer_fans": 8_000, "wikipedia_monthly_views": 4_000,
        "wikipedia_trend": 1.4, "instagram_followers": 210_000, "instagram_engagement_rate": 0.012,
        "tiktok_followers": 1_800_000, "tiktok_engagement_rate": 0.09, "shows_24mo": 6, "countries_24mo": 1,
        "upcoming_shows": 4,
        "_festivals": [],
        "_growth": 0.30,
    },
}


def seed_demo(store: Store, today: date | None = None) -> list[int]:
    today = today or date.today()
    ids = []
    for name, spec in DEMO_ARTISTS.items():
        if any(a["name"] == name for a in store.list_artists()):
            continue
        artist_id = store.create_artist(name, None, ArtistLinks())
        growth = spec["_growth"]
        festivals = [FestivalAppearance(n, tier, today - timedelta(days=days), role, "demo")
                     for n, tier, days, role in spec["_festivals"]]
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for months_back in (2, 1, 0):
            factor = (1 + growth) ** -months_back
            metrics = {}
            for key, value in spec.items():
                if key.startswith("_"):
                    continue
                grows = key.endswith(("_followers", "_listeners", "_subscribers", "_fans"))
                metrics[key] = Metric(key, round(value * factor) if grows else value, "demo", "synthetic demo value")
            metrics["festival_score"] = Metric("festival_score", festival_score(festivals, today), "demo")
            derive_metrics(metrics)
            store.add_snapshot(artist_id, metrics, {"festivals": [f.to_dict() for f in festivals], "shows": [],
                                                    "upcoming": []},
                               {"demo": {"status": "ok", "error": None, "metrics": sorted(metrics),
                                         "label": "Synthetic demo data", "url": None}},
                               fetched_at=(now - timedelta(days=30 * months_back)).isoformat())
        ids.append(artist_id)
    return ids

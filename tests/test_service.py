from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import respx

from artistscore.models import ArtistLinks, Metric
from artistscore.service import Service
from artistscore.storage import Store
from tests.conftest import DictSettings, fixture_json
from tests.fakes import DEFAULT_FAKES, fake_source

TODAY = date(2026, 10, 7)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "s.db")


def make_service(store, sources=DEFAULT_FAKES, tmp_path=None, settings=None):
    return Service(store, DictSettings(settings), sources=sources, today_fn=lambda: TODAY,
                   weights_path=(tmp_path / "weights.yaml") if tmp_path else None)


async def test_refresh_stores_snapshot_with_statuses_and_merged_metrics(store):
    service = make_service(store)
    artist_id = store.create_artist("Test Artist", "mbid-1", ArtistLinks(mbid="mbid-1"))
    await service.refresh(artist_id)
    snap = store.snapshots(artist_id)[-1]
    assert snap["sources"]["youtube"]["status"] == "error"
    assert snap["sources"]["youtube"]["error"] == "HTTP 403"
    assert snap["sources"]["lastfm"]["status"] == "skipped"
    assert snap["sources"]["spotify"]["status"] == "ok"
    metrics = snap["metrics"]
    assert metrics["shows_24mo"].value == 40  # max across sources
    assert metrics["spotify_follower_ratio"].value == pytest.approx(0.25)
    # Coachella deduped to the headliner record (20 pts, ~0.5y decay) + Pitchfork tier 2 (5 pts, ~1.2y decay)
    assert metrics["festival_score"].value == pytest.approx(20 * 0.5 ** (171 / 365.25 / 2) + 5 * 0.5 ** (444 / 365.25 / 2),
                                                           rel=0.01)
    assert len(snap["details"]["festivals"]) == 2


async def test_discovered_links_are_saved(store):
    service = make_service(store)
    artist_id = store.create_artist("Test Artist", None, ArtistLinks())
    await service.refresh(artist_id)
    assert store.get_artist(artist_id)["links"].deezer_id == "399"


async def test_source_exception_never_fails_refresh(store):
    service = make_service(store, [fake_source("bad", raises=RuntimeError("kaboom")),
                                   fake_source("deezer", {"deezer_fans": 10_000})])
    artist_id = store.create_artist("A", None, ArtistLinks())
    await service.refresh(artist_id)
    report = service.report(artist_id)
    assert report["sources"]["bad"]["status"] == "error"
    assert report["score"].total is not None


async def test_report_without_links_has_low_coverage(store):
    service = make_service(store, [fake_source("spotify", status="skipped"), fake_source("deezer", {"deezer_fans": 5_000})])
    artist_id = store.create_artist("Unknown", None, ArtistLinks())
    await service.refresh(artist_id)
    report = service.report(artist_id)
    assert report["score"].coverage < 0.4
    assert report["score"].confidence == "low"


def test_report_before_any_refresh(store):
    service = make_service(store)
    artist_id = store.create_artist("New", None, ArtistLinks())
    report = service.report(artist_id)
    assert report["score"].total is None
    assert report["fetched_at"] is None


async def test_overrides_beat_fetched_values(store):
    service = make_service(store)
    artist_id = store.create_artist("Test Artist", None, ArtistLinks())
    await service.refresh(artist_id)
    store.set_overrides(artist_id, {"spotify_monthly_listeners": 50_000_000, "avg_ticket_sales": 5000})
    report = service.report(artist_id)
    assert report["metrics"]["spotify_monthly_listeners"].value == 50_000_000
    assert report["metrics"]["spotify_monthly_listeners"].source == "manual"
    assert report["metrics"]["avg_ticket_sales"].value == 5000
    assert report["metrics"]["spotify_follower_ratio"].value == pytest.approx(0.01)


def test_momentum_from_history(store):
    service = make_service(store)
    artist_id = store.create_artist("A", None, ArtistLinks())
    t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    store.add_snapshot(artist_id, {"spotify_monthly_listeners": Metric("spotify_monthly_listeners", 100_000, "spotify")},
                       {}, {}, fetched_at=t0.isoformat())
    store.add_snapshot(artist_id, {"spotify_monthly_listeners": Metric("spotify_monthly_listeners", 125_000, "spotify")},
                       {}, {}, fetched_at=(t0 + timedelta(days=30)).isoformat())
    report = service.report(artist_id)
    assert report["metrics"]["streaming_growth_30d"].value == pytest.approx(0.25)
    assert len(report["history"]) == 2
    assert report["history"][1]["total"] > report["history"][0]["total"]


def test_weights_save_and_reset(store, tmp_path):
    service = make_service(store, tmp_path=tmp_path)
    weights = service.weights()
    weights["pillars"]["reach"]["weight"] = 99
    service.save_weights(weights)
    assert service.weights()["pillars"]["reach"]["weight"] == 99
    service.reset_weights()
    assert service.weights()["pillars"]["reach"]["weight"] == 25


@respx.mock
async def test_add_artist_resolves_links_and_is_idempotent(store):
    respx.get("https://musicbrainz.org/ws/2/artist/mbid-1").respond(200, json=fixture_json("musicbrainz_artist_urls.json"))
    respx.get("https://www.wikidata.org/wiki/Special:EntityData/Q42.json").respond(200, json=fixture_json("wikidata_entity.json"))
    service = make_service(store)
    first = await service.add_artist("mbid-1", "Test Artist")
    assert store.get_artist(first)["links"].instagram == "testartist"
    assert await service.add_artist("mbid-1", "Test Artist") == first


@respx.mock
async def test_add_artist_survives_musicbrainz_outage(store):
    respx.get("https://musicbrainz.org/ws/2/artist/mbid-9").mock(side_effect=httpx.ConnectError("down"))
    service = make_service(store)
    artist_id = await service.add_artist("mbid-9", "Someone")
    assert store.get_artist(artist_id)["links"].mbid == "mbid-9"


async def test_disabled_sources_are_not_run(store):
    service = make_service(store, settings={"DISABLED_SOURCES": "spotify"})
    artist_id = store.create_artist("Test Artist", None, ArtistLinks())
    await service.refresh(artist_id)
    assert store.snapshots(artist_id)[-1]["sources"]["spotify"]["status"] == "skipped"

from artistscore.config import Settings
from artistscore.models import ArtistLinks, Metric
from artistscore.storage import Store


def make_store(tmp_path):
    return Store(tmp_path / "t.db")


def test_artist_roundtrip(tmp_path):
    store = make_store(tmp_path)
    links = ArtistLinks(mbid="abc", spotify_id="sp1", instagram="radiohead")
    artist_id = store.create_artist("Radiohead", "abc", links)
    artist = store.get_artist(artist_id)
    assert artist["name"] == "Radiohead"
    assert artist["links"].spotify_id == "sp1"
    assert artist["links"].instagram == "radiohead"
    assert [a["id"] for a in store.list_artists()] == [artist_id]

    store.update_links(artist_id, ArtistLinks(mbid="abc", tiktok="rh"))
    assert store.get_artist(artist_id)["links"].tiktok == "rh"
    assert store.get_artist(artist_id)["links"].spotify_id is None


def test_snapshots_ordered_oldest_first(tmp_path):
    store = make_store(tmp_path)
    artist_id = store.create_artist("A", None, ArtistLinks())
    store.add_snapshot(artist_id, {"x": Metric("x", 1.0, "s")}, {}, {}, fetched_at="2026-01-01T00:00:00+00:00")
    store.add_snapshot(artist_id, {"x": Metric("x", 2.0, "s")}, {"shows": [1]}, {"s": {"status": "ok"}},
                       fetched_at="2026-02-01T00:00:00+00:00")
    snaps = store.snapshots(artist_id)
    assert [s["metrics"]["x"].value for s in snaps] == [1.0, 2.0]
    assert snaps[1]["details"] == {"shows": [1]}
    assert snaps[1]["sources"]["s"]["status"] == "ok"
    assert snaps[0]["fetched_at"] == "2026-01-01T00:00:00+00:00"


def test_overrides_roundtrip(tmp_path):
    store = make_store(tmp_path)
    artist_id = store.create_artist("A", None, ArtistLinks())
    assert store.get_artist(artist_id)["overrides"] == {}
    store.set_overrides(artist_id, {"avg_ticket_sales": 1200.0})
    assert store.get_artist(artist_id)["overrides"] == {"avg_ticket_sales": 1200.0}


def test_settings_override_env(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    monkeypatch.setenv("LASTFM_API_KEY", "from-env")
    settings = Settings(store)
    assert settings.get("LASTFM_API_KEY") == "from-env"
    store.set_setting("LASTFM_API_KEY", "from-ui")
    assert settings.get("LASTFM_API_KEY") == "from-ui"
    store.set_setting("LASTFM_API_KEY", "")
    assert settings.get("LASTFM_API_KEY") == "from-env"


def test_delete_artist(tmp_path):
    store = make_store(tmp_path)
    artist_id = store.create_artist("A", None, ArtistLinks())
    store.add_snapshot(artist_id, {}, {}, {})
    store.delete_artist(artist_id)
    assert store.list_artists() == []
    assert store.snapshots(artist_id) == []

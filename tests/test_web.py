from datetime import date

import pytest
import respx
from fastapi.testclient import TestClient

from artistscore.models import ArtistLinks
from artistscore.service import Service
from artistscore.storage import Store
from artistscore.web.app import create_app
from tests.conftest import fixture_json
from tests.fakes import DEFAULT_FAKES


@pytest.fixture
def service(tmp_path):
    store = Store(tmp_path / "w.db")
    return Service(store, sources=DEFAULT_FAKES, weights_path=tmp_path / "weights.yaml",
                   today_fn=lambda: date(2026, 10, 7))


@pytest.fixture
def client(service):
    return TestClient(create_app(service))


def test_index_empty(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "No artists yet" in response.text


@respx.mock
def test_search_lists_candidates(client):
    respx.get("https://musicbrainz.org/ws/2/artist").respond(200, json=fixture_json("musicbrainz_search.json"))
    response = client.get("/search", params={"q": "Test Artist"})
    assert response.status_code == 200
    assert "UK rock band" in response.text and "rapper" in response.text


@respx.mock
def test_add_artist_refreshes_and_redirects(client, service):
    respx.get("https://musicbrainz.org/ws/2/artist/mbid-1").respond(200, json=fixture_json("musicbrainz_artist_urls.json"))
    respx.get("https://www.wikidata.org/wiki/Special:EntityData/Q42.json").respond(200, json=fixture_json("wikidata_entity.json"))
    response = client.post("/artists", data={"mbid": "mbid-1", "name": "Test Artist"}, follow_redirects=False)
    assert response.status_code == 303
    artist_id = int(response.headers["location"].rsplit("/", 1)[1])
    assert len(service.store.snapshots(artist_id)) == 1  # background refresh ran


def _seeded(client, service):
    artist_id = service.store.create_artist("Test Artist", None, ArtistLinks())
    client.post(f"/artist/{artist_id}/refresh")
    return artist_id


def test_artist_page_shows_score_pillars_and_sources(client, service):
    artist_id = _seeded(client, service)
    page = client.get(f"/artist/{artist_id}").text
    total = service.report(artist_id)["score"].total
    assert f"{total:.0f}" in page
    assert "Live demand &amp; track record" in page
    assert "HTTP 403" in page  # failing source is explained
    assert "Coachella" in page


def test_artist_json_export(client, service):
    artist_id = _seeded(client, service)
    data = client.get(f"/artist/{artist_id}.json").json()
    assert data["artist"]["name"] == "Test Artist"
    assert data["score"]["total"] == pytest.approx(service.report(artist_id)["score"].total)
    assert data["metrics"]["deezer_fans"]["value"] == 100_000


def test_unknown_artist_404(client):
    assert client.get("/artist/999").status_code == 404


def test_overrides_form(client, service):
    artist_id = _seeded(client, service)
    client.post(f"/artist/{artist_id}/overrides", data={"avg_ticket_sales": "2,500", "x_followers": ""})
    assert service.store.get_artist(artist_id)["overrides"] == {"avg_ticket_sales": 2500.0}
    client.post(f"/artist/{artist_id}/overrides", data={"avg_ticket_sales": ""})
    assert service.store.get_artist(artist_id)["overrides"] == {}


def test_overrides_accept_thousands_and_decimal(client, service):
    artist_id = _seeded(client, service)
    client.post(f"/artist/{artist_id}/overrides", data={"avg_ticket_sales": "1,234.5"})
    assert service.store.get_artist(artist_id)["overrides"] == {"avg_ticket_sales": 1234.5}


def test_links_form(client, service):
    artist_id = _seeded(client, service)
    client.post(f"/artist/{artist_id}/links", data={"spotify_id": " https://open.spotify.com/artist/abc ",
                                                    "instagram": "@someone", "tiktok": ""})
    links = service.store.get_artist(artist_id)["links"]
    assert links.spotify_id == "abc"  # a pasted URL is reduced to the ID
    assert links.instagram == "someone"
    assert links.tiktok is None


def test_weights_change_rescores(client, service):
    artist_id = _seeded(client, service)
    before = service.report(artist_id)["score"].total
    form = {f"pillar__{k}": str(p["weight"]) for k, p in service.weights()["pillars"].items()}
    form["pillar__live"] = "0"
    client.post("/weights", data=form)
    assert service.weights()["pillars"]["live"]["weight"] == 0
    assert service.report(artist_id)["score"].total != pytest.approx(before)
    client.post("/weights/reset")
    assert service.weights()["pillars"]["live"]["weight"] == 30


def test_weights_rejects_negative(client, service):
    response = client.post("/weights", data={"pillar__live": "-5"})
    assert response.status_code == 400
    assert service.weights()["pillars"]["live"]["weight"] == 30


@pytest.mark.parametrize("value", ["inf", "nan", "-inf"])
def test_weights_rejects_non_finite(client, service, value):
    response = client.post("/weights", data={"pillar__live": value})
    assert response.status_code == 400
    assert service.weights()["pillars"]["live"]["weight"] == 30


def test_settings_saves_and_masks_keys(client, service):
    client.post("/settings", data={"LASTFM_API_KEY": "secret-value-123"})
    assert service.store.get_setting("LASTFM_API_KEY") == "secret-value-123"
    page = client.get("/settings").text
    assert "secret-value-123" not in page
    assert "set" in page
    # blank submission keeps the saved key
    client.post("/settings", data={"LASTFM_API_KEY": ""})
    assert service.store.get_setting("LASTFM_API_KEY") == "secret-value-123"
    client.post("/settings", data={"clear__LASTFM_API_KEY": "on"})
    assert service.store.get_setting("LASTFM_API_KEY") == ""


def test_cross_site_post_is_blocked(client, service):
    response = client.post("/settings", data={"LASTFM_API_KEY": "evil"}, headers={"Origin": "https://evil.example"},
                           follow_redirects=False)
    assert response.status_code == 403
    assert not service.store.get_setting("LASTFM_API_KEY")


def test_same_origin_post_is_allowed(client, service):
    response = client.post("/settings", data={"LASTFM_API_KEY": "good"}, headers={"Origin": "http://testserver"},
                           follow_redirects=False)
    assert response.status_code == 303
    assert service.store.get_setting("LASTFM_API_KEY") == "good"


def test_cross_site_referer_is_blocked(client, service):
    response = client.post("/settings", data={"LASTFM_API_KEY": "evil"},
                           headers={"Referer": "https://evil.example/page"}, follow_redirects=False)
    assert response.status_code == 403
    assert not service.store.get_setting("LASTFM_API_KEY")


def test_null_origin_is_blocked(client, service):
    response = client.post("/settings", data={"LASTFM_API_KEY": "evil"}, headers={"Origin": "null"},
                           follow_redirects=False)
    assert response.status_code == 403
    assert not service.store.get_setting("LASTFM_API_KEY")


def test_compare_and_csv(client, service):
    a = _seeded(client, service)
    b = service.store.create_artist("Second", None, ArtistLinks())
    page = client.get("/compare", params=[("ids", a), ("ids", b)]).text
    assert "Test Artist" in page and "Second" in page
    csv = client.get("/export.csv").text
    assert csv.splitlines()[0].startswith("artist,total,tier,coverage")
    assert "Test Artist" in csv


def test_delete_artist(client, service):
    artist_id = _seeded(client, service)
    client.post(f"/artist/{artist_id}/delete")
    assert service.store.get_artist(artist_id) is None


def test_delete_confirm_survives_apostrophes(client, service):
    artist_id = service.store.create_artist("Guns N' Roses", None, ArtistLinks())
    page = client.get(f"/artist/{artist_id}").text
    form = page[page.index(f'action="/artist/{artist_id}/delete"'):]
    form = form[: form.index("</form>")]
    handler = form[form.index("onsubmit="):]
    assert "Guns N" not in handler  # the name is not spliced into the JS handler
    assert 'data-name="Guns N&#39; Roses"' in form
    assert "this.dataset.name" in form

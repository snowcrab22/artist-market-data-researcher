import httpx
import pytest
import respx

from artistscore.sources import deezer, instagram, musicbrainz_events, soundcloud, spotify, tiktok, wikipedia
from artistscore.sources.base import parse_count, run_source
from tests.conftest import fixture_json, fixture_text


@pytest.mark.parametrize("text,expected", [("11.6M", 11_600_000), ("12,345", 12_345), ("1 234", 1_234),
                                           ("987", 987), ("2.5K", 2_500), ("1.2B", 1_200_000_000),
                                           ("1 234 567", 1_234_567), ("", None), ("n/a", None)])
def test_parse_count(text, expected):
    assert parse_count(text) == expected


@respx.mock
async def test_spotify_monthly_listeners_from_meta(make_ctx):
    respx.get("https://open.spotify.com/artist/sp1").respond(200, text=fixture_text("spotify_artist.html"))
    result = await run_source(spotify, make_ctx(spotify_id="sp1"))
    assert result.status == "ok"
    # the exact count in the page body beats the rounded meta value
    assert result.metrics["spotify_monthly_listeners"].value == 11_612_345
    assert "spotify_followers" not in result.metrics


@respx.mock
async def test_spotify_followers_from_embedded_state(make_ctx):
    respx.get("https://open.spotify.com/artist/sp2").respond(200, text=fixture_text("spotify_artist_state.html"))
    result = await run_source(spotify, make_ctx(spotify_id="sp2"))
    assert result.metrics["spotify_monthly_listeners"].value == 2_312_877
    assert result.metrics["spotify_followers"].value == 845_123


async def test_spotify_without_id_is_skipped(make_ctx):
    result = await run_source(spotify, make_ctx())
    assert result.status == "skipped"


@respx.mock
async def test_spotify_http_error_is_error(make_ctx):
    respx.get("https://open.spotify.com/artist/sp1").respond(500)
    result = await run_source(spotify, make_ctx(spotify_id="sp1"))
    assert result.status == "error"
    assert "500" in result.error


@respx.mock
async def test_spotify_page_without_numbers_is_error(make_ctx):
    respx.get("https://open.spotify.com/artist/sp1").respond(200, text="<html></html>")
    result = await run_source(spotify, make_ctx(spotify_id="sp1"))
    assert result.status == "error"


@respx.mock
async def test_deezer_by_id(make_ctx):
    respx.get("https://api.deezer.com/artist/399").respond(200, json=fixture_json("deezer_artist.json"))
    result = await run_source(deezer, make_ctx(deezer_id="399"))
    assert result.metrics["deezer_fans"].value == 4_123_456


@respx.mock
async def test_deezer_search_picks_exact_name(make_ctx):
    respx.get("https://api.deezer.com/search/artist").respond(200, json=fixture_json("deezer_search.json"))
    respx.get("https://api.deezer.com/artist/399").respond(200, json=fixture_json("deezer_artist.json"))
    result = await run_source(deezer, make_ctx(name="radiohead"))
    assert result.metrics["deezer_fans"].value == 4_123_456
    assert result.details["deezer_id"] == "399"


@respx.mock
async def test_deezer_search_without_exact_match_is_skipped(make_ctx):
    respx.get("https://api.deezer.com/search/artist").respond(200, json={"data": [{"id": 1, "name": "Other"}]})
    result = await run_source(deezer, make_ctx(name="Radiohead"))
    assert result.status == "skipped"


@respx.mock
async def test_deezer_error_payload_is_error(make_ctx):
    respx.get("https://api.deezer.com/artist/1").respond(200, json={"error": {"type": "DataException", "message": "no data"}})
    result = await run_source(deezer, make_ctx(deezer_id="1"))
    assert result.status == "error"


@respx.mock
async def test_wikipedia_monthly_views_and_trend(make_ctx):
    route = respx.get(url__regex=r"https://wikimedia\.org/api/rest_v1/metrics/pageviews/per-article/en\.wikipedia/"
                                 r"all-access/user/The_Smile_%28band%29/monthly/2025100100/2026093000")
    route.respond(200, json=fixture_json("wikipedia_pageviews.json"))
    result = await run_source(wikipedia, make_ctx(wikipedia_title="The Smile (band)"))
    assert route.called
    assert result.metrics["wikipedia_monthly_views"].value == 200_000
    assert result.metrics["wikipedia_trend"].value == pytest.approx(1.0)


@respx.mock
async def test_wikipedia_other_language_prefix(make_ctx):
    route = respx.get(url__startswith="https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/fr.wikipedia/")
    route.respond(200, json=fixture_json("wikipedia_pageviews.json"))
    result = await run_source(wikipedia, make_ctx(wikipedia_title="fr:Stromae"))
    assert result.status == "ok"


@respx.mock
async def test_musicbrainz_events_festivals_and_shows(make_ctx):
    respx.get("https://musicbrainz.org/ws/2/event").respond(200, json=fixture_json("musicbrainz_events.json"))
    result = await run_source(musicbrainz_events, make_ctx(mbid="mbid-1"))
    fests = result.details["festivals"]
    assert {(f["name"], f["tier"], f["role"]) for f in fests} == {
        ("Coachella", 1, "headliner"), ("Green Valley Summer Festival", 3, None)}
    # within 24 months of 2026-10-07: Coachella 2025 and Brixton 2025-11; the 2024-07 festival is older
    assert result.metrics["shows_24mo"].value == 2
    assert len(result.details["shows"]) == 4


@respx.mock
async def test_soundcloud_followers(make_ctx):
    respx.get("https://soundcloud.com/testartist").respond(200, text=fixture_text("soundcloud_profile.html"))
    result = await run_source(soundcloud, make_ctx(soundcloud="testartist"))
    assert result.metrics["soundcloud_followers"].value == 48_213


@respx.mock
async def test_tiktok_followers_and_engagement(make_ctx):
    respx.get("https://www.tiktok.com/@testartist").respond(200, text=fixture_text("tiktok_profile.html"))
    result = await run_source(tiktok, make_ctx(tiktok="testartist"))
    assert result.metrics["tiktok_followers"].value == 200_000
    # 5M likes / 100 videos = 50K avg likes per video; / 200K followers = 25%
    assert result.metrics["tiktok_engagement_rate"].value == pytest.approx(0.25)


@respx.mock
async def test_tiktok_zero_videos_has_no_engagement_rate(make_ctx):
    html = fixture_text("tiktok_profile.html").replace('"videoCount": 100', '"videoCount": 0')
    respx.get("https://www.tiktok.com/@testartist").respond(200, text=html)
    result = await run_source(tiktok, make_ctx(tiktok="testartist"))
    assert "tiktok_engagement_rate" not in result.metrics
    assert result.metrics["tiktok_followers"].value == 200_000


@respx.mock
async def test_instagram_followers_and_engagement(make_ctx):
    respx.get("https://i.instagram.com/api/v1/users/web_profile_info/").respond(
        200, json=fixture_json("instagram_profile.json"))
    result = await run_source(instagram, make_ctx(instagram="testartist"))
    assert result.metrics["instagram_followers"].value == 50_000
    assert result.metrics["instagram_engagement_rate"].value == pytest.approx(1000 / 50_000)


@respx.mock
async def test_instagram_login_wall_is_error(make_ctx):
    respx.get("https://i.instagram.com/api/v1/users/web_profile_info/").respond(401, json={"message": "login_required"})
    result = await run_source(instagram, make_ctx(instagram="testartist"))
    assert result.status == "error"
    assert "manual" in result.error.lower()


@respx.mock
async def test_network_failure_is_error(make_ctx):
    respx.get("https://soundcloud.com/x").mock(side_effect=httpx.ConnectError("boom"))
    result = await run_source(soundcloud, make_ctx(soundcloud="x"))
    assert result.status == "error"


@respx.mock
async def test_spotify_ignores_followers_of_other_entities(make_ctx):
    html = ('<html><head><meta property="og:description" content="Artist · 2.3M monthly listeners."/></head><body>'
            '<script>{"playlist":{"name":"Hits","followers":98765432}}' + " " * 400 +
            '{"stats":{"monthlyListeners":2312877,"worldRank":0}}</script>'
            '<div>Top playlist · 5.1M followers</div></body></html>')
    respx.get("https://open.spotify.com/artist/sp3").respond(200, text=html)
    result = await run_source(spotify, make_ctx(spotify_id="sp3"))
    assert result.metrics["spotify_monthly_listeners"].value == 2_312_877
    assert "spotify_followers" not in result.metrics

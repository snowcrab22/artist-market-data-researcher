import pytest
import respx

from artistscore.sources import bandsintown, lastfm, setlistfm, spotify_api, ticketmaster, youtube
from artistscore.sources.base import run_source
from tests.conftest import fixture_json

YT = "https://www.googleapis.com/youtube/v3"


@pytest.mark.parametrize("module", [lastfm, youtube, setlistfm, ticketmaster, bandsintown, spotify_api])
async def test_missing_key_is_skipped(module, make_ctx):
    result = await run_source(module, make_ctx(mbid="mbid-1", spotify_id="sp", youtube_channel_id="UC123"))
    assert result.status == "skipped"
    assert "key" in result.error.lower() or "app_id" in result.error.lower() or "client" in result.error.lower()


@respx.mock
async def test_lastfm_listeners_plays_and_ratio(make_ctx):
    route = respx.get("https://ws.audioscrobbler.com/2.0/").respond(200, json=fixture_json("lastfm_artist.json"))
    result = await run_source(lastfm, make_ctx(mbid="mbid-1", settings={"LASTFM_API_KEY": "k"}))
    assert route.calls[0].request.url.params["mbid"] == "mbid-1"
    assert result.metrics["lastfm_listeners"].value == 250_000
    assert result.metrics["lastfm_plays_per_listener"].value == pytest.approx(30)


@respx.mock
async def test_lastfm_falls_back_to_name_when_mbid_unknown(make_ctx):
    route = respx.get("https://ws.audioscrobbler.com/2.0/").mock(side_effect=[
        respx.MockResponse(200, json={"error": 6, "message": "The artist you supplied could not be found"}),
        respx.MockResponse(200, json=fixture_json("lastfm_artist.json"))])
    result = await run_source(lastfm, make_ctx(mbid="mbid-1", settings={"LASTFM_API_KEY": "k"}))
    assert route.calls[1].request.url.params["artist"] == "Test Artist"
    assert result.status == "ok"


@respx.mock
async def test_lastfm_zero_listeners_has_no_ratio(make_ctx):
    payload = fixture_json("lastfm_artist.json")
    payload["artist"]["stats"] = {"listeners": "0", "playcount": "0"}
    respx.get("https://ws.audioscrobbler.com/2.0/").respond(200, json=payload)
    result = await run_source(lastfm, make_ctx(settings={"LASTFM_API_KEY": "k"}))
    assert "lastfm_plays_per_listener" not in result.metrics


@respx.mock
async def test_youtube_stats_and_engagement(make_ctx):
    respx.get(f"{YT}/channels").respond(200, json=fixture_json("youtube_channel.json"))
    respx.get(f"{YT}/playlistItems").respond(200, json=fixture_json("youtube_playlist.json"))
    respx.get(f"{YT}/videos").respond(200, json=fixture_json("youtube_videos.json"))
    result = await run_source(youtube, make_ctx(youtube_channel_id="UC123", settings={"YOUTUBE_API_KEY": "k"}))
    assert result.metrics["youtube_subscribers"].value == 1_200_000
    assert result.metrics["youtube_views"].value == 500_000_000
    assert result.metrics["youtube_engagement_rate"].value == pytest.approx(8000 / 200_000)


@respx.mock
async def test_youtube_search_skips_topic_channels(make_ctx):
    respx.get(f"{YT}/search").respond(200, json=fixture_json("youtube_search.json"))
    channels = respx.get(f"{YT}/channels").respond(200, json=fixture_json("youtube_channel.json"))
    respx.get(f"{YT}/playlistItems").respond(200, json={"items": []})
    result = await run_source(youtube, make_ctx(settings={"YOUTUBE_API_KEY": "k"}))
    assert channels.calls[0].request.url.params["id"] == "UC123"
    assert result.details["links"] == {"youtube_channel_id": "UC123"}
    assert "youtube_engagement_rate" not in result.metrics


@respx.mock
async def test_youtube_handle_lookup(make_ctx):
    channels = respx.get(f"{YT}/channels").respond(200, json=fixture_json("youtube_channel.json"))
    respx.get(f"{YT}/playlistItems").respond(200, json={"items": []})
    await run_source(youtube, make_ctx(youtube_handle="testartist", settings={"YOUTUBE_API_KEY": "k"}))
    assert channels.calls[0].request.url.params["forHandle"] == "@testartist"


@respx.mock
async def test_setlistfm_shows_countries_and_festivals(make_ctx):
    base = "https://api.setlist.fm/rest/1.0/artist/mbid-1/setlists"
    route = respx.get(base).mock(side_effect=[respx.MockResponse(200, json=fixture_json("setlistfm_p1.json")),
                                              respx.MockResponse(200, json=fixture_json("setlistfm_p2.json"))])
    result = await run_source(setlistfm, make_ctx(mbid="mbid-1", settings={"SETLISTFM_API_KEY": "k"}))
    assert route.calls[0].request.headers["x-api-key"] == "k"
    # past shows within 24 months of 2026-10-07: 2026-09-20, 2026-04-12, 2025-08-03, 2025-03-01 (2024-03-01 too old,
    # 2026-12-01 is in the future)
    assert result.metrics["shows_24mo"].value == 4
    assert result.metrics["countries_24mo"].value == 3  # GB, US, NL
    fests = {(f["name"], f["tier"]) for f in result.details["festivals"]}
    # Coachella by venue; the generic "Festival Grounds" venue counts; "Festival Tour 2026" tour name does not
    assert fests == {("Coachella", 1), ("Riverside Music Festival Grounds", 3)}


@respx.mock
async def test_setlistfm_404_means_no_shows(make_ctx):
    respx.get("https://api.setlist.fm/rest/1.0/artist/mbid-1/setlists").respond(404)
    result = await run_source(setlistfm, make_ctx(mbid="mbid-1", settings={"SETLISTFM_API_KEY": "k"}))
    assert result.status == "ok"
    assert result.metrics["shows_24mo"].value == 0


@respx.mock
async def test_ticketmaster_upcoming_and_festivals(make_ctx):
    respx.get("https://app.ticketmaster.com/discovery/v2/attractions.json").respond(
        200, json=fixture_json("ticketmaster_attractions.json"))
    respx.get("https://app.ticketmaster.com/discovery/v2/events.json").respond(
        200, json=fixture_json("ticketmaster_events.json"))
    result = await run_source(ticketmaster, make_ctx(settings={"TICKETMASTER_API_KEY": "k"}))
    assert result.metrics["upcoming_shows"].value == 14
    assert [(f["name"], f["date"]) for f in result.details["festivals"]] == [("Lollapalooza", "2027-07-30")]
    assert len(result.details["upcoming"]) == 2


@respx.mock
async def test_bandsintown_trackers(make_ctx):
    respx.get("https://rest.bandsintown.com/artists/Test%20Artist").respond(200, json=fixture_json("bandsintown_artist.json"))
    result = await run_source(bandsintown, make_ctx(settings={"BANDSINTOWN_APP_ID": "a"}))
    assert result.metrics["bandsintown_trackers"].value == 345_678
    assert result.metrics["upcoming_shows"].value == 9


@respx.mock
async def test_bandsintown_unknown_artist_is_skipped(make_ctx):
    respx.get("https://rest.bandsintown.com/artists/Test%20Artist").respond(200, text="")
    result = await run_source(bandsintown, make_ctx(settings={"BANDSINTOWN_APP_ID": "a"}))
    assert result.status == "skipped"


@respx.mock
async def test_spotify_api_followers_when_returned(make_ctx):
    respx.post("https://accounts.spotify.com/api/token").respond(200, json={"access_token": "t", "expires_in": 3600})
    respx.get("https://api.spotify.com/v1/artists/sp").respond(
        200, json={"id": "sp", "name": "Test Artist", "followers": {"total": 900000}, "popularity": 71})
    result = await run_source(spotify_api, make_ctx(spotify_id="sp", settings={
        "SPOTIFY_CLIENT_ID": "i", "SPOTIFY_CLIENT_SECRET": "s"}))
    assert result.metrics["spotify_followers"].value == 900_000
    assert result.metrics["spotify_popularity"].value == 71


@respx.mock
async def test_spotify_api_without_followers_field_resolves_id_only(make_ctx):
    respx.post("https://accounts.spotify.com/api/token").respond(200, json={"access_token": "t"})
    respx.get("https://api.spotify.com/v1/search").respond(
        200, json={"artists": {"items": [{"id": "spX", "name": "Test Artist"}]}})
    respx.get("https://api.spotify.com/v1/artists/spX").respond(200, json={"id": "spX", "name": "Test Artist"})
    result = await run_source(spotify_api, make_ctx(settings={"SPOTIFY_CLIENT_ID": "i", "SPOTIFY_CLIENT_SECRET": "s"}))
    assert result.status == "ok"
    assert result.metrics == {}
    assert result.details["links"] == {"spotify_id": "spX"}

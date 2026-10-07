import httpx
import respx

from artistscore import resolve
from tests.conftest import fixture_json


@respx.mock
async def test_search_returns_candidates():
    respx.get("https://musicbrainz.org/ws/2/artist").respond(200, json=fixture_json("musicbrainz_search.json"))
    async with httpx.AsyncClient() as client:
        results = await resolve.search(client, "Test Artist")
    assert [r["mbid"] for r in results] == ["mbid-1", "mbid-2"]
    assert results[0]["disambiguation"] == "UK rock band"
    assert results[0]["begin"] == "1991"


@respx.mock
async def test_links_from_musicbrainz_and_wikidata():
    respx.get("https://musicbrainz.org/ws/2/artist/mbid-1").respond(200, json=fixture_json("musicbrainz_artist_urls.json"))
    respx.get("https://www.wikidata.org/wiki/Special:EntityData/Q42.json").respond(200, json=fixture_json("wikidata_entity.json"))
    async with httpx.AsyncClient() as client:
        links = await resolve.links_for(client, "mbid-1")
    assert links.mbid == "mbid-1"
    assert links.spotify_id == "4Z8W4fKeB5YxbusRsdQVPb"  # MusicBrainz wins over Wikidata
    assert links.instagram == "testartist"
    assert links.youtube_channel_id == "UC123"  # www.youtube.com preferred over music.youtube.com
    assert links.deezer_id == "399"
    assert links.lastfm_name == "Test Artist"
    assert links.twitter == "testartist"
    assert links.soundcloud == "testartist"
    assert links.wikidata_id == "Q42"
    assert links.tiktok == "testartist_tt"  # filled from Wikidata
    assert links.wikipedia_title == "Test Artist (band)"


def test_parse_url_variants():
    assert resolve.parse_url("https://www.youtube.com/@TestArtist").youtube_handle == "TestArtist"
    assert resolve.parse_url("https://www.tiktok.com/@test.artist?lang=en").tiktok == "test.artist"
    assert resolve.parse_url("https://x.com/testartist").twitter == "testartist"
    assert resolve.parse_url("https://www.deezer.com/en/artist/12").deezer_id == "12"
    assert resolve.parse_url("https://en.wikipedia.org/wiki/The_Smile_(band)").wikipedia_title == "The Smile (band)"
    assert resolve.parse_url("https://www.instagram.com/explore/tags/x/").instagram is None
    assert resolve.parse_url("https://example.com/") == resolve.ArtistLinks()


@respx.mock
async def test_wikidata_failure_keeps_musicbrainz_links():
    respx.get("https://musicbrainz.org/ws/2/artist/mbid-1").respond(200, json=fixture_json("musicbrainz_artist_urls.json"))
    respx.get("https://www.wikidata.org/wiki/Special:EntityData/Q42.json").respond(500)
    async with httpx.AsyncClient() as client:
        links = await resolve.links_for(client, "mbid-1")
    assert links.spotify_id == "4Z8W4fKeB5YxbusRsdQVPb"
    assert links.tiktok is None

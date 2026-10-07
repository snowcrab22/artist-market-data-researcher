"""Identity resolution: artist name -> MusicBrainz candidates; MBID -> platform links (MusicBrainz + Wikidata)."""

from __future__ import annotations

import re
from urllib.parse import unquote, unquote_plus, urlsplit

import httpx

from artistscore import http
from artistscore.models import ArtistLinks

MB = "https://musicbrainz.org/ws/2"
WIKIDATA = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIDATA_PROPS = {"P1902": "spotify_id", "P2003": "instagram", "P7085": "tiktok", "P2397": "youtube_channel_id",
                  "P2722": "deezer_id", "P3040": "soundcloud", "P2002": "twitter", "P3192": "lastfm_name"}
RESERVED_PATHS = {"explore", "p", "reel", "reels", "stories", "intent", "share", "hashtag", "i", "home", "search"}
LUCENE_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')


async def search(client: httpx.AsyncClient, name: str) -> list[dict]:
    payload = await http.get_json(client, f"{MB}/artist", params={
        "query": LUCENE_SPECIAL.sub(r"\\\1", name), "fmt": "json", "limit": 10})
    return [{"mbid": a["id"], "name": a["name"], "disambiguation": a.get("disambiguation", ""),
             "country": a.get("country", ""), "type": a.get("type", ""), "score": a.get("score", 0),
             "begin": (a.get("life-span") or {}).get("begin", "")}
            for a in payload.get("artists", [])]


def _first_segment(path: str) -> str:
    return unquote(path.strip("/").split("/")[0]) if path.strip("/") else ""


def parse_url(url: str) -> ArtistLinks:
    """Extract whichever platform identifier a profile URL carries."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path = parts.path
    segs = [s for s in path.split("/") if s]
    links = ArtistLinks()
    if host == "open.spotify.com" and len(segs) >= 2 and segs[-2] == "artist":
        links.spotify_id = segs[-1]
    elif host == "youtube.com" and segs:
        if segs[0] == "channel" and len(segs) > 1:
            links.youtube_channel_id = segs[1]
        elif segs[0].startswith("@"):
            links.youtube_handle = segs[0][1:]
        elif segs[0] in ("user", "c") and len(segs) > 1:
            links.youtube_handle = segs[1]
    elif host == "instagram.com" and segs and segs[0] not in RESERVED_PATHS:
        links.instagram = segs[0]
    elif host == "tiktok.com" and segs and segs[0].startswith("@"):
        links.tiktok = segs[0][1:]
    elif host in ("twitter.com", "x.com") and segs and segs[0] not in RESERVED_PATHS:
        links.twitter = segs[0]
    elif host == "soundcloud.com" and segs:
        links.soundcloud = segs[0]
    elif host == "deezer.com" and "artist" in segs and segs.index("artist") + 1 < len(segs):
        links.deezer_id = segs[segs.index("artist") + 1]
    elif host in ("last.fm", "lastfm.com") and len(segs) >= 2 and segs[0] == "music":
        links.lastfm_name = unquote_plus(segs[1])
    elif host == "wikidata.org" and len(segs) >= 2 and segs[0] == "wiki":
        links.wikidata_id = segs[1]
    elif host.endswith("wikipedia.org") and len(segs) >= 2 and segs[0] == "wiki":
        lang = host.split(".")[0]
        title = unquote(segs[1]).replace("_", " ")
        links.wikipedia_title = title if lang == "en" else f"{lang}:{title}"
    elif host == "bandsintown.com" and len(segs) >= 2 and segs[0] == "a":
        pass  # numeric Bandsintown IDs are not accepted by the public API; the artist name is used instead
    return links


async def _wikidata_links(client: httpx.AsyncClient, qid: str) -> ArtistLinks:
    entity = (await http.get_json(client, WIKIDATA.format(qid=qid)))["entities"][qid]
    links = ArtistLinks()
    for prop, field in WIKIDATA_PROPS.items():
        claims = entity.get("claims", {}).get(prop) or []
        value = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value") if claims else None
        if isinstance(value, str):
            setattr(links, field, value)
    enwiki = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
    if enwiki:
        links.wikipedia_title = enwiki
    return links


async def links_for(client: httpx.AsyncClient, mbid: str) -> ArtistLinks:
    payload = await http.get_json(client, f"{MB}/artist/{mbid}", params={"inc": "url-rels", "fmt": "json"})
    links = ArtistLinks(mbid=mbid)
    urls = [rel.get("url", {}).get("resource", "") for rel in payload.get("relations", [])]
    # Prefer canonical hosts (www.youtube.com over music.youtube.com) by processing them first.
    for url in sorted(urls, key=lambda u: "music.youtube.com" in u):
        if "music.youtube.com" in url:
            continue
        links.fill_missing(parse_url(url))
    if links.wikidata_id:
        try:
            links.fill_missing(await _wikidata_links(client, links.wikidata_id))
        except (httpx.HTTPError, KeyError, ValueError):
            pass  # Wikidata only adds optional links
    return links

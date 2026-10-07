"""Command line: `artistscore serve | search | score | doctor | demo`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import webbrowser

import httpx

from artistscore import http
from artistscore.config import KEYS, Settings, data_dir, load_dotenv
from artistscore.storage import Store

DOCTOR_URLS = {
    "MusicBrainz": "https://musicbrainz.org/ws/2/artist?query=radiohead&fmt=json&limit=1",
    "Wikidata": "https://www.wikidata.org/wiki/Special:EntityData/Q44190.json",
    "Spotify page": "https://open.spotify.com/artist/4Z8W4fKeB5YxbusRsdQVPb",
    "Deezer": "https://api.deezer.com/artist/399",
    "Wikipedia pageviews": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Radiohead/monthly/2025010100/2025020100",
    "Last.fm": "https://ws.audioscrobbler.com/2.0/",
    "YouTube": "https://www.googleapis.com/youtube/v3/channels",
    "setlist.fm": "https://api.setlist.fm/rest/1.0/",
    "Ticketmaster": "https://app.ticketmaster.com/discovery/v2/",
    "Bandsintown": "https://rest.bandsintown.com/",
    "Instagram": "https://i.instagram.com/",
    "TikTok": "https://www.tiktok.com/",
    "SoundCloud": "https://soundcloud.com/",
}


def _service():
    from artistscore.service import Service

    store = Store(data_dir() / "artistscore.db")
    return Service(store, Settings(store), weights_path=data_dir() / "weights.yaml")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from artistscore.web.app import create_app

    url = f"http://{args.host}:{args.port}"
    print(f"ArtistScore running at {url}  (data: {data_dir().resolve()})")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


async def _search(name: str) -> list[dict]:
    return await _service().search(name)


def cmd_search(args: argparse.Namespace) -> None:
    for c in asyncio.run(_search(args.name)):
        extra = ", ".join(x for x in (c["type"], c["country"], c["disambiguation"], c["begin"]) if x)
        print(f"{c['mbid']}  {c['name']}  ({extra})  score={c['score']}")


async def _score(args: argparse.Namespace) -> dict:
    service = _service()
    mbid, name = args.mbid, args.name
    if not mbid:
        candidates = await service.search(args.name)
        if not candidates:
            raise SystemExit(f"No MusicBrainz match for {args.name!r}; try `artistscore search`.")
        mbid, name = candidates[0]["mbid"], candidates[0]["name"]
        print(f"Using {name} ({candidates[0]['disambiguation'] or candidates[0]['country'] or mbid}); "
              f"pass --mbid to choose another.", file=sys.stderr)
    artist_id = await service.add_artist(mbid, name)
    await service.refresh(artist_id)
    return service.report(artist_id)


def cmd_score(args: argparse.Namespace) -> None:
    report = asyncio.run(_score(args))
    score = report["score"]
    if args.json:
        print(json.dumps({"artist": report["artist"]["name"], "score": score.to_dict(),
                          "sources": report["sources"]}, indent=2, default=str))
        return
    total = "n/a" if score.total is None else f"{score.total:.1f}"
    print(f"\n{report['artist']['name']}: {total} / 100  ({score.tier}; coverage {score.coverage:.0%}, "
          f"{score.confidence} confidence)\n")
    for pillar in score.pillars.values():
        value = "  —  " if pillar.score is None else f"{pillar.score:5.1f}"
        print(f"  {pillar.label:<30} {value}   (weight {pillar.weight:g})")
        for m in pillar.metrics:
            print(f"      {m.label:<48} {m.value:>16,.4g}  → {m.score:5.1f}  [{m.source}]")
    print("\nSources:")
    for name, info in report["sources"].items():
        print(f"  {name:<20} {info['status']:<8} {info.get('error') or ''}")


async def _doctor() -> None:
    settings = Settings(Store(data_dir() / "artistscore.db"))
    print("API keys:")
    for key, (label, url) in KEYS.items():
        print(f"  {'✓' if settings.get(key) else '·'} {label:<45} {'' if settings.get(key) else url}")
    print("\nConnectivity:")
    async with http.make_client() as client:
        for name, url in DOCTOR_URLS.items():
            try:
                response = await client.get(url, headers={"User-Agent": http.BROWSER_UA})
                status = f"reachable (HTTP {response.status_code})"
            except httpx.HTTPError as exc:
                status = f"UNREACHABLE: {type(exc).__name__}"
            print(f"  {name:<22} {status}")


def cmd_doctor(_: argparse.Namespace) -> None:
    asyncio.run(_doctor())


def cmd_demo(_: argparse.Namespace) -> None:
    from artistscore.demo import seed_demo

    ids = seed_demo(Store(data_dir() / "artistscore.db"))
    print(f"Seeded {len(ids)} synthetic demo artists." if ids else "Demo artists already present.")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="artistscore", description="Aggregate artist market metrics into a score.")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the local web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--open", action="store_true", help="open a browser tab")
    serve.set_defaults(func=cmd_serve)
    search = sub.add_parser("search", help="find MusicBrainz candidates for a name")
    search.add_argument("name")
    search.set_defaults(func=cmd_search)
    score = sub.add_parser("score", help="fetch and score one artist")
    score.add_argument("name")
    score.add_argument("--mbid", help="MusicBrainz ID (skips the name search)")
    score.add_argument("--json", action="store_true")
    score.set_defaults(func=cmd_score)
    doctor = sub.add_parser("doctor", help="check API keys and connectivity to each platform")
    doctor.set_defaults(func=cmd_doctor)
    demo = sub.add_parser("demo", help="add synthetic demo artists to explore the UI")
    demo.set_defaults(func=cmd_demo)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except httpx.HTTPError as exc:
        raise SystemExit(f"Network error: {type(exc).__name__}: {exc}. "
                         "Run `artistscore doctor` to check which platforms are reachable.") from exc


if __name__ == "__main__":
    main()

"""Shared HTTP helpers: client factory, polite per-host rate limiting, one retry on 429/5xx."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from artistscore import __version__

PROJECT_URL = "https://github.com/snowcrab22/artist-market-data-researcher"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0.0.0 Safari/537.36")

# Minimum seconds between requests to a host (MusicBrainz asks for <= 1 req/s, setlist.fm <= 2 req/s).
HOST_INTERVALS: dict[str, float] = {"musicbrainz.org": 1.1, "api.setlist.fm": 0.6, "www.wikidata.org": 0.2}
RETRY_BACKOFF = 2.0
RETRY_STATUSES = {429, 500, 502, 503, 504}

_last_request: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}


def user_agent(contact: str | None = None) -> str:
    return f"ArtistScore/{__version__} (+{PROJECT_URL}{'; ' + contact if contact else ''})"


def make_client(contact: str | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                             headers={"User-Agent": user_agent(contact), "Accept-Language": "en"})


async def _throttle(host: str) -> None:
    interval = HOST_INTERVALS.get(host)
    if not interval:
        return
    lock = _locks.setdefault(host, asyncio.Lock())
    async with lock:
        wait = _last_request.get(host, 0.0) + interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request[host] = time.monotonic()


async def get(client: httpx.AsyncClient, url: str, *, params: dict[str, Any] | None = None,
              headers: dict[str, str] | None = None, retries: int = 1) -> httpx.Response:
    """GET with throttling and a retry on 429/5xx. Raises httpx.HTTPStatusError for non-2xx responses."""
    host = urlsplit(url).hostname or ""
    for attempt in range(retries + 1):
        await _throttle(host)
        response = await client.get(url, params=params, headers=headers)
        if response.status_code in RETRY_STATUSES and attempt < retries:
            retry_after = response.headers.get("Retry-After", "")
            delay = min(float(retry_after), 10.0) if retry_after.isdigit() else RETRY_BACKOFF * (attempt + 1)
            await asyncio.sleep(delay)
            continue
        response.raise_for_status()
        return response
    raise AssertionError("unreachable")


async def get_json(client: httpx.AsyncClient, url: str, **kwargs: Any) -> Any:
    return (await get(client, url, **kwargs)).json()

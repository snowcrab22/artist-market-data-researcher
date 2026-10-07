"""Settings: API keys and options. Values saved in the UI override environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artistscore.storage import Store

# key -> (label, where to get it)
KEYS: dict[str, tuple[str, str]] = {
    "LASTFM_API_KEY": ("Last.fm API key", "https://www.last.fm/api/account/create"),
    "YOUTUBE_API_KEY": ("YouTube Data API v3 key", "https://console.cloud.google.com/apis/library/youtube.googleapis.com"),
    "SETLISTFM_API_KEY": ("setlist.fm API key", "https://www.setlist.fm/settings/api"),
    "TICKETMASTER_API_KEY": ("Ticketmaster Discovery API key", "https://developer.ticketmaster.com/"),
    "BANDSINTOWN_APP_ID": ("Bandsintown app_id", "https://help.artists.bandsintown.com/en/articles/9186477-api-documentation"),
    "SPOTIFY_CLIENT_ID": ("Spotify client ID (optional)", "https://developer.spotify.com/dashboard"),
    "SPOTIFY_CLIENT_SECRET": ("Spotify client secret (optional)", "https://developer.spotify.com/dashboard"),
    "CONTACT_EMAIL": ("Contact email for MusicBrainz User-Agent", "https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting"),
    "DISABLED_SOURCES": ("Disabled sources (comma-separated)", ""),
}

SECRET_KEYS = {k for k in KEYS if k.endswith(("_KEY", "_SECRET", "_APP_ID"))}


def data_dir() -> Path:
    path = Path(os.environ.get("ARTISTSCORE_DATA_DIR", "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings:
    def __init__(self, store: "Store | None" = None) -> None:
        self.store = store

    def get(self, key: str) -> str | None:
        if self.store is not None:
            value = self.store.get_setting(key)
            if value:
                return value
        return os.environ.get(key) or None

    def disabled_sources(self) -> set[str]:
        raw = self.get("DISABLED_SOURCES") or ""
        return {s.strip() for s in raw.split(",") if s.strip()}


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env reader: KEY=VALUE lines; existing environment variables win."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        os.environ.setdefault(key, value.strip("'\""))

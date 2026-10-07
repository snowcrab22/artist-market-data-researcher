"""SQLite persistence: artists, metric snapshots and settings."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from artistscore.models import ArtistLinks, Metric

SCHEMA = """
CREATE TABLE IF NOT EXISTS artists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    mbid TEXT,
    links_json TEXT NOT NULL DEFAULT '{}',
    overrides_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    fetched_at TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    details_json TEXT NOT NULL,
    sources_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_artist ON snapshots(artist_id, fetched_at);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # --- artists ---------------------------------------------------------
    def create_artist(self, name: str, mbid: str | None, links: ArtistLinks) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO artists (name, mbid, links_json, created_at) VALUES (?, ?, ?, ?)",
                (name, mbid, json.dumps(links.to_dict()), utcnow_iso()),
            )
            return int(cur.lastrowid)

    def _artist_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "mbid": row["mbid"],
            "links": ArtistLinks.from_dict(json.loads(row["links_json"])),
            "overrides": {k: float(v) for k, v in json.loads(row["overrides_json"]).items()},
            "created_at": row["created_at"],
        }

    def get_artist(self, artist_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM artists WHERE id = ?", (artist_id,)).fetchone()
        return self._artist_row(row) if row else None

    def find_by_mbid(self, mbid: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM artists WHERE mbid = ?", (mbid,)).fetchone()
        return self._artist_row(row) if row else None

    def list_artists(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM artists ORDER BY name COLLATE NOCASE").fetchall()
        return [self._artist_row(r) for r in rows]

    def update_links(self, artist_id: int, links: ArtistLinks) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE artists SET links_json = ? WHERE id = ?",
                         (json.dumps(links.to_dict()), artist_id))

    def set_overrides(self, artist_id: int, overrides: dict[str, float]) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE artists SET overrides_json = ? WHERE id = ?",
                         (json.dumps(overrides), artist_id))

    def delete_artist(self, artist_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM snapshots WHERE artist_id = ?", (artist_id,))
            conn.execute("DELETE FROM artists WHERE id = ?", (artist_id,))

    # --- snapshots -------------------------------------------------------
    def add_snapshot(self, artist_id: int, metrics: dict[str, Metric], details: dict[str, Any],
                     sources: dict[str, Any], fetched_at: str | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO snapshots (artist_id, fetched_at, metrics_json, details_json, sources_json)"
                " VALUES (?, ?, ?, ?, ?)",
                (artist_id, fetched_at or utcnow_iso(),
                 json.dumps({k: m.to_dict() for k, m in metrics.items()}),
                 json.dumps(details, default=str), json.dumps(sources, default=str)),
            )
            return int(cur.lastrowid)

    def snapshots(self, artist_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshots WHERE artist_id = ? ORDER BY fetched_at, id", (artist_id,)
            ).fetchall()
        return [
            {
                "id": r["id"],
                "fetched_at": r["fetched_at"],
                "metrics": {k: Metric.from_dict(v) for k, v in json.loads(r["metrics_json"]).items()},
                "details": json.loads(r["details_json"]),
                "sources": json.loads(r["sources_json"]),
            }
            for r in rows
        ]

    # --- settings --------------------------------------------------------
    def get_setting(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

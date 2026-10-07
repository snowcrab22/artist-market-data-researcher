"""Orchestration: resolve artists, run every source concurrently, store snapshots, build score reports."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import yaml

from artistscore import http, resolve
from artistscore.config import Settings
from artistscore.festivals import dedupe, festival_score
from artistscore.models import ArtistLinks, FestivalAppearance, Metric, SourceResult
from artistscore.scoring import engine
from artistscore.sources import ALL_SOURCES
from artistscore.sources.base import SourceContext, run_source
from artistscore.storage import Store

# Counts that several sources report independently; the largest is the most complete.
MAX_MERGE = {"shows_24mo", "countries_24mo", "upcoming_shows"}
# Sources whose show history is complete enough that "no festivals found" is itself a measurement.
FESTIVAL_AUTHORITATIVE = {"setlistfm"}


def derive_metrics(metrics: dict[str, Metric]) -> None:
    """Add metrics computed from other metrics (in place)."""
    listeners = metrics.get("spotify_monthly_listeners")
    followers = metrics.get("spotify_followers")
    if listeners and followers and listeners.value > 0:
        metrics["spotify_follower_ratio"] = Metric("spotify_follower_ratio", followers.value / listeners.value,
                                                   "derived", "Spotify followers ÷ monthly listeners")


class Service:
    def __init__(self, store: Store, settings: Settings | None = None, sources: list[ModuleType] | None = None,
                 client_factory: Callable[[], httpx.AsyncClient] | None = None,
                 weights_path: str | Path | None = None, today_fn: Callable[[], date] = date.today) -> None:
        self.store = store
        self.settings = settings or Settings(store)
        self.sources = ALL_SOURCES if sources is None else sources
        self.client_factory = client_factory or (lambda: http.make_client(self.settings.get("CONTACT_EMAIL")))
        self.weights_path = Path(weights_path) if weights_path else None
        self.today_fn = today_fn

    # --- artists -----------------------------------------------------------
    async def search(self, name: str) -> list[dict]:
        async with self.client_factory() as client:
            return await resolve.search(client, name)

    async def add_artist(self, mbid: str, name: str) -> int:
        existing = self.store.find_by_mbid(mbid)
        if existing:
            return existing["id"]
        try:
            async with self.client_factory() as client:
                links = await resolve.links_for(client, mbid)
        except (httpx.HTTPError, KeyError, ValueError):
            links = ArtistLinks(mbid=mbid)  # links can be filled in by hand later
        return self.store.create_artist(name, mbid, links)

    def add_manual_artist(self, name: str) -> int:
        return self.store.create_artist(name, None, ArtistLinks())

    # --- refresh -----------------------------------------------------------
    async def refresh(self, artist_id: int) -> int:
        artist = self.store.get_artist(artist_id)
        if artist is None:
            raise KeyError(artist_id)
        disabled = self.settings.disabled_sources()
        today = self.today_fn()
        async with self.client_factory() as client:
            ctx = SourceContext(artist["name"], artist["links"], self.settings, client, today)
            active = [m for m in self.sources if m.NAME not in disabled]
            results: list[SourceResult] = list(await asyncio.gather(*(run_source(m, ctx) for m in active)))
        results += [SourceResult.skipped(m.NAME, "disabled in settings") for m in self.sources if m.NAME in disabled]

        metrics: dict[str, Metric] = {}
        festivals: list[FestivalAppearance] = []
        shows: list[dict] = []
        upcoming: list[dict] = []
        discovered = ArtistLinks()
        for result in results:
            if result.status != "ok":
                continue
            for key, metric in result.metrics.items():
                current = metrics.get(key)
                if current is None or (key in MAX_MERGE and metric.value > current.value):
                    metrics[key] = metric
            festivals += [FestivalAppearance.from_dict(f) for f in result.details.get("festivals", [])]
            shows += result.details.get("shows", [])
            upcoming += result.details.get("upcoming", [])
            discovered.fill_missing(ArtistLinks.from_dict(result.details.get("links")))

        festivals = dedupe(festivals)
        authoritative = any(r.status == "ok" and r.source in FESTIVAL_AUTHORITATIVE for r in results)
        if festivals or authoritative:
            metrics["festival_score"] = Metric("festival_score", festival_score(festivals, today), "derived",
                                               f"{len(festivals)} festival appearances in the catalog window")
        derive_metrics(metrics)

        links = artist["links"]
        before = links.to_dict()
        links.fill_missing(discovered)
        if links.to_dict() != before:
            self.store.update_links(artist_id, links)

        sources = {
            r.source: {"status": r.status, "error": r.error, "metrics": sorted(r.metrics),
                       "label": next((getattr(m, "LABEL", r.source) for m in self.sources if m.NAME == r.source), r.source),
                       "url": r.details.get("url")}
            for r in results
        }
        details = {
            "festivals": [f.to_dict() for f in festivals],
            "shows": sorted(shows, key=lambda s: s.get("date", ""), reverse=True)[:150],
            "upcoming": sorted(upcoming, key=lambda s: s.get("date", ""))[:100],
        }
        return self.store.add_snapshot(artist_id, metrics, details, sources)

    # --- weights -----------------------------------------------------------
    def weights(self) -> dict[str, Any]:
        if self.weights_path and self.weights_path.exists():
            return engine.load_weights(self.weights_path)
        return engine.default_weights()

    def save_weights(self, weights: dict[str, Any]) -> None:
        if not self.weights_path:
            raise RuntimeError("no weights path configured")
        self.weights_path.write_text(yaml.safe_dump(weights, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def reset_weights(self) -> None:
        if self.weights_path and self.weights_path.exists():
            self.weights_path.unlink()

    # --- reports -----------------------------------------------------------
    @staticmethod
    def _with_momentum(snaps: list[dict], upto: int) -> dict[str, Metric]:
        metrics = dict(snaps[upto]["metrics"])
        series = [{k: m.value for k, m in s["metrics"].items()} for s in snaps[: upto + 1]]
        stamps = [datetime.fromisoformat(s["fetched_at"]) for s in snaps[: upto + 1]]
        for key, value in engine.derive_momentum(series, stamps).items():
            metrics[key] = Metric(key, value, "history", "computed from stored snapshots")
        return metrics

    def report(self, artist_id: int, weights: dict[str, Any] | None = None) -> dict[str, Any]:
        artist = self.store.get_artist(artist_id)
        if artist is None:
            raise KeyError(artist_id)
        weights = weights or self.weights()
        snaps = self.store.snapshots(artist_id)

        history = []
        for i, snap in enumerate(snaps):
            metrics_i = self._with_momentum(snaps, i)
            result = engine.score({k: m.value for k, m in metrics_i.items()}, weights)
            history.append({"fetched_at": snap["fetched_at"], "total": result.total, "tier": result.tier,
                            "coverage": result.coverage})

        metrics = self._with_momentum(snaps, len(snaps) - 1) if snaps else {}
        for key, value in artist["overrides"].items():
            metrics[key] = Metric(key, value, "manual", "entered by hand")
        if "spotify_monthly_listeners" in artist["overrides"] or "spotify_followers" in artist["overrides"]:
            derive_metrics(metrics)
        score = engine.score({k: m.value for k, m in metrics.items()}, weights,
                             {k: m.source for k, m in metrics.items()})
        latest = snaps[-1] if snaps else {"details": {}, "sources": {}, "fetched_at": None}
        return {"artist": artist, "score": score, "metrics": metrics, "details": latest["details"],
                "sources": latest["sources"], "fetched_at": latest["fetched_at"], "history": history}

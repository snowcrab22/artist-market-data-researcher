"""Local web UI (FastAPI + Jinja2, no JS build step)."""

from __future__ import annotations

import csv
import io
import logging
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from artistscore import __version__, resolve
from artistscore.config import KEYS, SECRET_KEYS, data_dir
from artistscore.models import ArtistLinks
from artistscore.service import Service
from artistscore.sources.base import parse_count
from artistscore.storage import Store
from artistscore.web import formatting

HERE = Path(__file__).parent
log = logging.getLogger("artistscore")

LINK_LABELS = {
    "mbid": "MusicBrainz ID", "spotify_id": "Spotify artist ID", "youtube_channel_id": "YouTube channel ID (UC…)",
    "youtube_handle": "YouTube @handle", "instagram": "Instagram handle", "tiktok": "TikTok handle",
    "soundcloud": "SoundCloud slug", "twitter": "X / Twitter handle", "deezer_id": "Deezer artist ID",
    "lastfm_name": "Last.fm artist name", "wikipedia_title": "Wikipedia article (fr:Title for other languages)",
    "wikidata_id": "Wikidata ID (Q…)", "bandsintown_name": "Bandsintown artist name",
}


def clean_link(field: str, raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return getattr(resolve.parse_url(value), field, None) or value
    if field in ("instagram", "tiktok", "twitter", "youtube_handle"):
        value = value.lstrip("@")
    return value


def create_app(service: Service | None = None) -> FastAPI:
    if service is None:
        store = Store(data_dir() / "artistscore.db")
        service = Service(store, weights_path=data_dir() / "weights.yaml")
    app = FastAPI(title="ArtistScore", version=__version__)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    formatting.register(templates.env)
    jobs: dict[int, str] = {}

    @app.middleware("http")
    async def block_cross_site_writes(request: Request, call_next):
        # Browsers always send Origin on cross-site form POSTs; curl and scripts send neither header.
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin is None and "referer" in request.headers:
                origin = request.headers["referer"]
            # "Origin: null" has no host, so it never matches and is blocked too
            if origin is not None and urlsplit(origin).netloc != request.headers.get("host"):
                return PlainTextResponse("Cross-site request blocked", status_code=403)
        return await call_next(request)

    def render(request: Request, name: str, status_code: int = 200, **ctx: Any) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {"version": __version__, **ctx}, status_code=status_code)

    def artist_or_404(artist_id: int) -> dict:
        artist = service.store.get_artist(artist_id)
        if artist is None:
            raise HTTPException(404, "Artist not found")
        return artist

    async def run_refresh(artist_id: int) -> None:
        jobs[artist_id] = "running"
        try:
            await service.refresh(artist_id)
            jobs.pop(artist_id, None)
        except Exception as exc:  # surfaced on the artist page
            log.exception("refresh failed")
            jobs[artist_id] = f"Refresh failed: {exc}"

    def start_refresh(artist_id: int, tasks: BackgroundTasks) -> None:
        if jobs.get(artist_id) != "running":
            jobs[artist_id] = "running"
            tasks.add_task(run_refresh, artist_id)

    def see_other(url: str) -> RedirectResponse:
        return RedirectResponse(url, status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        rows = [service.report(a["id"]) for a in service.store.list_artists()]
        rows.sort(key=lambda r: -1 if r["score"].total is None else r["score"].total, reverse=True)
        return render(request, "index.html", rows=rows, jobs=jobs)

    @app.get("/search", response_class=HTMLResponse)
    async def search(request: Request, q: str = ""):
        candidates, error = [], None
        if q.strip():
            try:
                candidates = await service.search(q.strip())
            except Exception as exc:
                error = f"MusicBrainz search failed ({type(exc).__name__}). You can still add the artist manually."
        return render(request, "search.html", q=q, candidates=candidates, error=error)

    @app.post("/artists")
    async def add_artist(request: Request, tasks: BackgroundTasks):
        form = await request.form()
        artist_id = await service.add_artist(str(form["mbid"]), str(form["name"]))
        start_refresh(artist_id, tasks)
        return see_other(f"/artist/{artist_id}")

    @app.post("/artists/manual")
    async def add_manual(request: Request):
        form = await request.form()
        name = str(form.get("name", "")).strip()
        if not name:
            raise HTTPException(400, "Name required")
        return see_other(f"/artist/{service.add_manual_artist(name)}")

    @app.get("/artist/{artist_id}.json")
    def artist_json(artist_id: int):
        artist_or_404(artist_id)
        report = service.report(artist_id)
        artist = report["artist"]
        return JSONResponse({
            "artist": {"id": artist["id"], "name": artist["name"], "mbid": artist["mbid"],
                       "links": artist["links"].to_dict(), "overrides": artist["overrides"]},
            "fetched_at": report["fetched_at"],
            "score": report["score"].to_dict(),
            "metrics": {k: m.to_dict() for k, m in report["metrics"].items()},
            "sources": report["sources"], "details": report["details"], "history": report["history"],
        })

    @app.get("/artist/{artist_id}", response_class=HTMLResponse)
    def artist_page(request: Request, artist_id: int):
        artist_or_404(artist_id)
        report = service.report(artist_id)
        return render(request, "artist.html", r=report, job=jobs.get(artist_id), link_labels=LINK_LABELS,
                      weights=service.weights())

    @app.post("/artist/{artist_id}/refresh")
    def refresh(artist_id: int, tasks: BackgroundTasks):
        artist_or_404(artist_id)
        start_refresh(artist_id, tasks)
        return see_other(f"/artist/{artist_id}")

    @app.post("/artist/{artist_id}/links")
    async def save_links(request: Request, artist_id: int):
        artist_or_404(artist_id)
        form = await request.form()
        values = {f: clean_link(f, str(form.get(f, ""))) for f in ArtistLinks.field_names()}
        service.store.update_links(artist_id, ArtistLinks.from_dict(values))
        return see_other(f"/artist/{artist_id}#links")

    @app.post("/artist/{artist_id}/overrides")
    async def save_overrides(request: Request, artist_id: int):
        artist = artist_or_404(artist_id)
        form = await request.form()
        overrides = dict(artist["overrides"])
        for key, raw in form.items():
            raw = str(raw).strip()
            if not raw:
                overrides.pop(key, None)
                continue
            value = parse_count(raw.rstrip("%"))
            if value is None:
                raise HTTPException(400, f"Could not read a number from {raw!r} for {key}")
            overrides[key] = value / 100 if raw.endswith("%") else value
        service.store.set_overrides(artist_id, overrides)
        return see_other(f"/artist/{artist_id}#manual")

    @app.post("/artist/{artist_id}/delete")
    def delete(artist_id: int):
        artist_or_404(artist_id)
        service.store.delete_artist(artist_id)
        return see_other("/")

    @app.get("/compare", response_class=HTMLResponse)
    def compare(request: Request, ids: list[int] | None = None):
        ids = ids or [a["id"] for a in service.store.list_artists()]
        reports = [service.report(i) for i in ids if service.store.get_artist(i)]
        return render(request, "compare.html", reports=reports, weights=service.weights())

    @app.get("/export.csv")
    def export_csv():
        weights = service.weights()
        metric_keys = [k for p in weights["pillars"].values() for k in p["metrics"]]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["artist", "total", "tier", "coverage", *[f"pillar_{k}" for k in weights["pillars"]],
                         *metric_keys])
        for artist in service.store.list_artists():
            report = service.report(artist["id"], weights)
            score = report["score"]
            writer.writerow([artist["name"], "" if score.total is None else round(score.total, 2), score.tier,
                             round(score.coverage, 3),
                             *["" if p.score is None else round(p.score, 2) for p in score.pillars.values()],
                             *[report["metrics"][k].value if k in report["metrics"] else "" for k in metric_keys]])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=artistscore.csv"})

    @app.get("/weights", response_class=HTMLResponse)
    def weights_page(request: Request, error: str | None = None):
        return render(request, "weights.html", weights=service.weights(), error=error,
                      customised=bool(service.weights_path and service.weights_path.exists()))

    @app.post("/weights")
    async def save_weights(request: Request):
        form = await request.form()
        weights = service.weights()
        try:
            for key, raw in form.items():
                parts = key.split("__")
                value = float(str(raw))
                if not math.isfinite(value):
                    raise ValueError("weights must be finite numbers")
                if value < 0:
                    raise ValueError("weights cannot be negative")
                if parts[0] == "pillar" and parts[1] in weights["pillars"]:
                    weights["pillars"][parts[1]]["weight"] = value
                elif parts[0] == "metric" and parts[1] in weights["pillars"] \
                        and parts[2] in weights["pillars"][parts[1]]["metrics"]:
                    weights["pillars"][parts[1]]["metrics"][parts[2]]["weight"] = value
        except ValueError as exc:
            return render(
                request, "weights.html", status_code=400, weights=service.weights(), error=f"Not saved: {exc}",
                customised=bool(service.weights_path and service.weights_path.exists()))
        service.save_weights(weights)
        return see_other("/weights?saved=1")

    @app.post("/weights/reset")
    def reset_weights():
        service.reset_weights()
        return see_other("/weights")

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        rows = []
        for key, (label, url) in KEYS.items():
            stored = service.store.get_setting(key) or ""
            effective = service.settings.get(key) or ""
            rows.append({"key": key, "label": label, "url": url, "secret": key in SECRET_KEYS,
                         "stored": stored, "effective": bool(effective), "from_env": bool(effective and not stored)})
        sources = [{"name": m.NAME, "label": m.LABEL, "requires": m.REQUIRES,
                    "ready": all(service.settings.get(k) for k in m.REQUIRES)} for m in service.sources]
        return render(request, "settings.html", rows=rows, sources=sources)

    @app.post("/settings")
    async def save_settings(request: Request):
        form = await request.form()
        for key in KEYS:
            if form.get(f"clear__{key}"):
                service.store.set_setting(key, "")
                continue
            value = str(form.get(key, "")).strip()
            if value or key not in SECRET_KEYS and key in form:
                service.store.set_setting(key, value)
        return see_other("/settings?saved=1")

    return app

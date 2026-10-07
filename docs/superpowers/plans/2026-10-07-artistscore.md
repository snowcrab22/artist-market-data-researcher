# ArtistScore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A locally hosted web app and CLI that gathers an artist's metrics from free platform APIs and public pages, and scores them 0–100 with the researched, editable weights.

**Architecture:** Async source modules each return a `SourceResult`. A service runs them concurrently and stores one SQLite snapshot per refresh. A pure scoring engine combines the latest snapshot, manual overrides, history and the YAML weights into a `ScoreResult`. FastAPI and Jinja2 render it.

**Tech Stack:** Python ≥3.11, FastAPI, Jinja2, httpx, PyYAML, uvicorn, python-multipart; tests use pytest, pytest-asyncio and respx.

**Spec:** `docs/superpowers/specs/2026-10-07-artistscore-design.md` (weights and anchors: `docs/research/metric-weights.md`)

## Global Constraints

- Python ≥ 3.11; no JS build step; no external CDN required for the UI to work.
- Data dir defaults to `./data` (env `ARTISTSCORE_DATA_DIR`); DB file `artistscore.db`.
- Pillar weights: live 30, reach 25, engagement 20, momentum 15, social 10. Metric weights and anchors exactly as in `metric-weights.md` §3.3.
- Tier cut-offs: ≥85 Superstar / headliner, ≥70 Established, ≥55 Mid-level, ≥35 Developing, else Emerging. Confidence: high ≥0.70 coverage, medium ≥0.40, else low.
- No source failure may fail a refresh; every source result carries `status` in {ok, skipped, error}.
- MusicBrainz requests ≤ 1/s with a descriptive User-Agent; setlist.fm ≤ 2/s.

## Review Focus

1. Artist with no MusicBrainz links at all → sources fall back to name search or report `skipped`; score still renders with low coverage (test in Task 6).
2. Number formats scraped from pages ("1.2M", "12,345", "1 234") → parsed correctly (test in Task 4, `parse_count`).
3. Two snapshots fewer than 14 days apart → no growth metric emitted (no divide-by-tiny-interval spikes) (test in Task 2).
4. Zero or negative values (0 views, 0 listeners) → log scale scores 0, no math error; ratio metrics are skipped when the denominator is 0 (tests in Tasks 2, 4).
5. User-edited weights with a pillar set to 0 or all metrics 0 → engine does not divide by zero (test in Task 2).

---

### Task 1: Project skeleton, models, storage

**Files:** Create `pyproject.toml`, `artistscore/__init__.py`, `artistscore/models.py`, `artistscore/config.py`, `artistscore/storage.py`, `tests/test_storage.py`, `.gitignore`.

**Interfaces – Produces:**
- `models.Metric(key: str, value: float, source: str, note: str | None = None)` (dataclass, `to_dict`/`from_dict`)
- `models.SourceResult(source: str, status: str, metrics: dict[str, Metric], details: dict, error: str | None)`
- `models.ArtistLinks` dataclass with optional str fields: `mbid, spotify_id, youtube_channel_id, youtube_handle, instagram, tiktok, soundcloud, twitter, deezer_id, lastfm_name, wikipedia_title, wikidata_id, bandsintown_name, setlistfm_mbid`.
- `config.Settings` with `get(key) -> str|None` (DB settings table wins over env) and `KEYS` list: `LASTFM_API_KEY, YOUTUBE_API_KEY, SETLISTFM_API_KEY, TICKETMASTER_API_KEY, BANDSINTOWN_APP_ID, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, CONTACT_EMAIL`.
- `storage.Store(path)`: `create_artist(name, mbid, links) -> int`, `get_artist(id) -> dict`, `list_artists() -> list[dict]`, `update_links(id, links)`, `set_overrides(id, dict[str,float])`, `add_snapshot(artist_id, metrics: dict[str, Metric], details: dict, sources: dict) -> int`, `snapshots(artist_id) -> list[dict]` (oldest first, `fetched_at` ISO UTC), `get_setting/set_setting`, `delete_artist(id)`.

- [ ] Test: `test_artist_roundtrip`, `test_snapshots_ordered_oldest_first`, `test_overrides_roundtrip`, `test_settings_override_env`.
- [ ] Run → fail; implement; run → pass; commit `feat: models, settings, sqlite store`.

### Task 2: Scoring engine

**Files:** Create `artistscore/scoring/__init__.py`, `weights.yaml`, `normalize.py`, `engine.py`; Test `tests/test_normalize.py`, `tests/test_engine.py`.

**Interfaces – Produces:**
- `normalize.log_scale(x, lo, hi) -> float`, `normalize.growth_score(g, full) -> float`, `normalize.benchmark_score(rate, followers, platform) -> float` with tables:
  TikTok expected ER by followers: <100K 7.5%, <500K 5.1%, <1M 4.48%, <5M 3.76%, <10M 3.3%, else 2.88%.
  Instagram: <10K 3.2%, <100K 1.55%, <500K 1.0%, <1M 0.65%, else 0.4%.
- `engine.load_weights(path=None) -> dict`, `engine.derive_momentum(history: list[dict[str, float]], timestamps: list[datetime]) -> dict[str, float]`, `engine.score(metrics: dict[str, float], weights: dict, sources: dict[str,str] | None = None) -> ScoreResult` with `ScoreResult.total, tier, coverage, confidence, pillars: dict[str, PillarScore]`, `PillarScore.score|None, weight, effective_weight, metrics: list[MetricScore(key,label,value,score,weight,effective_weight,contribution,source)]`; `ScoreResult.to_dict()`.

- [ ] Tests: `log_scale(50e6,1e3,50e6)==100`, `round(log_scale(5e5,1e3,50e6))==57`, `log_scale(0,...)==0`; `growth_score(0,0.25)==50`, `growth_score(0.25,0.25)==100`, `growth_score(-0.2,0.25)==0`; benchmark at expected → 50, 4× → 100; engine: all metrics present → coverage 1.0; only reach metrics → total equals reach pillar score and coverage 0.25; pillar weight 0 → no ZeroDivisionError; tier boundaries; `derive_momentum` with snapshots 10 days apart → `{}`; 30 days apart with ML 100→125 → streaming_growth_30d ≈ 0.25.
- [ ] Run → fail; implement; run → pass; commit `feat: scoring engine with researched weights`.

### Task 3: Festivals catalog

**Files:** Create `artistscore/festivals.yaml`, `artistscore/festivals.py`; Test `tests/test_festivals.py`.

**Interfaces – Produces:** `match_festival(*texts: str) -> tuple[str, int] | None` (name, tier; generic "festival"/"fest" word → ("<original text>", 3)), `festival_score(appearances: list[FestivalAppearance], today: date) -> float` with points T1 10/20 (headliner), T2 5/10, T3 2/3, half-life 2 years, window 5 years. `FestivalAppearance(name, tier, date, role, source)` lives in `models.py`; `dedupe(appearances)` by (name, year).

- [ ] Tests: "Coachella 2024" → ("Coachella", 1); venue "Empire Polo Club" → Coachella; "Some Town Fest" → tier 3; "Madison Square Garden" → None; score of one tier-1 appearance today = 10, two years ago = 5; duplicate Coachella from two sources counted once.
- [ ] Run → fail; implement; run → pass; commit.

### Task 4: HTTP layer + no-key sources

**Files:** Create `artistscore/http.py`, `artistscore/sources/__init__.py` (registry `ALL_SOURCES`), `base.py` (`SourceContext(name, links, settings, client, today)`, `parse_count(text)->float|None`), `spotify.py`, `deezer.py`, `wikipedia.py`, `musicbrainz_events.py`, `soundcloud.py`, `tiktok.py`, `instagram.py`; tests under `tests/sources/` with fixtures in `tests/fixtures/`.

**Interfaces – Produces:** each module exposes `NAME: str` and `async def fetch(ctx: SourceContext) -> SourceResult`. Metric keys exactly as in `metric-weights.md`. Details keys: `festivals` (list of FestivalAppearance dicts), `shows` (list of `{date, venue, city, country}`), `upcoming` (list).

- [ ] Tests (respx-mocked): `parse_count("11.6M")==11_600_000`, `"12,345"`, `"1 234"`, `"987"`; Spotify og:description → monthly listeners; Deezer `nb_fan`; Wikipedia 12 monthly items → avg of last 3 and trend; MB events with type Festival → festival appearances; TikTok rehydration JSON → followers + ER; Instagram JSON → followers + ER; SoundCloud `followers_count`; missing ID → `status == "skipped"`; HTTP 500 → `status == "error"`.
- [ ] Run → fail; implement; run → pass; commit.

### Task 5: Keyed sources + identity resolution

**Files:** Create `sources/lastfm.py`, `youtube.py`, `setlistfm.py`, `ticketmaster.py`, `bandsintown.py`, `spotify_api.py`, `artistscore/resolve.py`; tests + fixtures.

**Interfaces – Produces:** `resolve.search(client, name) -> list[dict(mbid,name,disambiguation,country,type,score)]`, `resolve.links_for(client, mbid) -> ArtistLinks` (MB url-rels parsed by URL host; then Wikidata P1902 Spotify, P2003 Instagram, P7085 TikTok, P2397 YouTube channel, P2722 Deezer, P3040 SoundCloud, P2002 X, enwiki sitelink — only filling fields MB left empty).

- [ ] Tests: Last.fm listeners/plays/plays-per-listener; YouTube stats + ER from 2 videos; setlist.fm 2 pages → shows_24mo counts only within 24 months, countries, festival match from venue name; Ticketmaster upcoming count; Bandsintown trackers; no key → skipped; MB url-rels → spotify id from `open.spotify.com/artist/<id>`, instagram handle, youtube `channel/UC…` vs `@handle`; Wikidata fills a missing TikTok.
- [ ] Run → fail; implement; run → pass; commit.

### Task 6: Service orchestration + CLI

**Files:** Create `artistscore/service.py`, `artistscore/cli.py`; Test `tests/test_service.py`.

**Interfaces – Produces:** `Service(store, settings, sources=ALL_SOURCES, client_factory=...)`: `async refresh(artist_id) -> int` (snapshot id; merges festival lists across sources via `dedupe`, computes `festival_score`, picks max of show counts), `report(artist_id) -> dict` (artist, latest metrics + overrides, score dict, history scores, details, source statuses), `async add_artist(mbid, name) -> int` (resolves links). CLI: `artistscore serve [--host --port]`, `artistscore search NAME`, `artistscore score NAME [--mbid]` (prints table/JSON), `artistscore doctor` (connectivity per host).

- [ ] Tests: fake sources (one ok, one error, one skipped) → snapshot stored, report has statuses and score; artist with no links → report renders, coverage < 0.4; overrides beat fetched values.
- [ ] Run → fail; implement; run → pass; commit.

### Task 7: Web UI

**Files:** Create `artistscore/web/app.py`, `templates/{base,index,search,artist,compare,weights,settings}.html`, `static/style.css`; Test `tests/test_web.py`.

**Interfaces – Consumes:** `Service`, `Store`, `engine.load_weights/save`. Routes per spec. Refresh runs as a background task; artist page shows "refreshing…" with a 3 s meta refresh while the job runs. Weights saved to `<data_dir>/weights.yaml`; `/weights/reset` deletes it.

- [ ] Tests: GET `/` 200; POST `/artists` with fake service creates artist and redirects; `/artist/{id}` shows total score text; `/weights` POST changes pillar weight and score changes; `/settings` saves a key (masked on display); `/artist/{id}.json` returns score dict.
- [ ] Run → fail; implement; run → pass; commit.

### Task 8: Packaging, docs, verification

**Files:** `README.md`, `.env.example`, `Dockerfile`, `docker-compose.yml`.

- [ ] Full `pytest` green; run `artistscore serve` with a seeded demo snapshot and screenshot pages with Playwright; `docker build` if the daemon is available.
- [ ] Commit and push to `claude/artist-metrics-aggregator-0ohibz`.

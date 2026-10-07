# ArtistScore: design spec

## Intent (from the request)

**What was asked:** an app that gathers data about a musical artist from every
relevant platform (monthly listeners, followers, engagement rates, past shows,
festival lineups), combines it into one aggregate score with researched
weights, can be used by other people, and runs locally. Whether an agent needs
to be in the loop was left for me to decide.

**Assumptions (made autonomously under `/goal`; open to correction):**
- The users are music-industry people (bookers, A&R, managers) or researchers
  comparing artists. They are not necessarily developers.
- "Usable by others" means one-command install, a browser UI, and API keys
  entered in the UI rather than in code.
- Free and free-tier data sources only. Paid aggregators (Chartmetric,
  Soundcharts) are out of scope.
- The score is meant for relative comparison, not dollar valuation.

**Success criteria**
1. Typing an artist name gives a disambiguated identity, then metrics from 10+
   platforms, then a 0–100 score with a pillar breakdown, coverage and the
   source of every number.
2. The weights are documented with citations (`docs/research/metric-weights.md`)
   and editable in the UI. Changing them rescores everything without
   re-fetching.
3. It runs locally with `pip install` or Docker. Missing API keys or blocked
   scrapers degrade gracefully, and any metric can be entered manually.
4. Repeated refreshes build history, and momentum comes from that history.

## Agent-in-the-loop decision: **no agent required**

Every step is deterministic. Platform IDs come from MusicBrainz and Wikidata
URL relations, metrics come from APIs or public pages, and scoring is a fixed
formula. The one ambiguous step, identity (several artists share a name), is
handled by showing the user MusicBrainz candidates with disambiguation and
letting them choose. An LLM would add cost, non-reproducible scores and an API
dependency for no accuracy gain. Fragile scrapers are handled with manual
overrides rather than an agent.

## Architecture

A Python 3.11+ package `artistscore`. It uses FastAPI with server-rendered
Jinja2 templates (no JS build step), httpx (async), SQLite and PyYAML.

```
artistscore/
  config.py         settings: env vars + settings table (UI-entered keys win)
  models.py         Metric, SourceResult, ArtistLinks, Show, FestivalAppearance
  http.py           shared AsyncClient, per-host rate limiting, UA
  resolve.py        name -> MusicBrainz candidates; MBID -> ArtistLinks (MB url-rels + Wikidata)
  festivals.py      festival catalog (festivals.yaml) + matching + festival_score
  sources/          one module per platform, each exposing `async fetch(ctx) -> SourceResult`
  scoring/          weights.yaml, normalize.py, engine.py (pure functions)
  storage.py        SQLite: artists, snapshots, settings
  service.py        orchestration: fetch all sources concurrently -> snapshot -> score
  web/              FastAPI app, templates, static css
  cli.py            `artistscore serve|score|search`
```

### Sources

| Source | Key needed | Metrics |
|---|---|---|
| MusicBrainz | no | identity, links, festival events (+ shows fallback) |
| Wikidata | no | extra links (Spotify, IG, TikTok, YouTube, Deezer, SoundCloud, X), enwiki title |
| Spotify public page | no | monthly listeners, followers (if present) |
| Spotify Web API | optional client id/secret | followers/popularity when still returned, ID search |
| Deezer API | no | fans |
| Last.fm API | free key | listeners, plays, plays/listener |
| YouTube Data API | free key | subscribers, views, engagement rate on the last 10 uploads |
| Wikipedia pageviews | no | monthly views, 3-vs-9-month trend |
| setlist.fm API | free key | shows in the last 24 months, countries, festival matches |
| Ticketmaster Discovery | free key | upcoming shows, festival matches |
| Bandsintown | app_id (by request) | trackers, upcoming shows |
| TikTok public page | no (best effort) | followers, likes, approximate engagement rate |
| Instagram web profile | no (best effort) | followers, engagement rate on the last 12 posts |
| SoundCloud public page | no (best effort) | followers |

Each source returns `SourceResult(status=ok|skipped|error)`. Sources run
concurrently, and one failing never fails the whole refresh. Skipped means a
key or ID is missing, and the UI says which.

### Scoring

The engine is pure. It takes `(metrics, history, weights)` and returns a
`ScoreResult`. Momentum metrics are derived from history by the engine. Manual
overrides are merged over fetched metrics before scoring. Normalisation, the
pillars, renormalisation and coverage are defined in
`docs/research/metric-weights.md`.

### Data flow

1. Search: MusicBrainz candidates are shown.
2. The user picks one, which creates an artist row with the MBID.
3. Resolve links from MusicBrainz and Wikidata (the user can edit them).
4. Refresh runs as a background job: all sources fetch, then one snapshot is
   stored.
5. The artist page computes the score from the latest snapshot, overrides,
   history and current weights.

### UI pages

`/` (tracked artists and search), `/search`, `/artist/{id}` (score, pillars,
metric table with sources, shows, festivals, links editor, manual overrides,
history, refresh, JSON export), `/compare`, `/weights` (edit and reset),
`/settings` (API keys and source status).

### Error handling

- HTTP: 20 s timeout, one retry on 429/5xx with backoff, and per-host rate
  limits (MusicBrainz 1/s, setlist.fm 2/s).
- Parser failures become `status=error` with a short message, shown in the
  "Sources" panel.

### Testing

- Pure unit tests for normalize, engine and festival matching.
- Source parsers tested against fixture payloads written to the documented
  response formats, with HTTP mocked by `respx`.
- Web tests use FastAPI TestClient with a fake source registry.
- Live endpoints cannot be reached from the build sandbox. That limitation is
  stated in the README, and a `artistscore doctor` command checks
  connectivity on the user's machine.

### Distribution

`pip install .` then `artistscore serve` opens http://127.0.0.1:8000. A
Dockerfile and `docker-compose.yml` mount the data dir as a volume. A
`.env.example` lists the keys and where to get each one.

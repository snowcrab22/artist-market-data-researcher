# ArtistScore

ArtistScore is a locally hosted app that gathers a musical artist's market data from
streaming, social and live-music platforms and turns it into a **0–100 score**. The
score's weights come from industry research. Every number shows its source, and you
can adjust the weights yourself.

* **Reach:** Spotify monthly listeners and followers, Last.fm listeners, YouTube
  subscribers and views, Deezer fans, Wikipedia pageviews
* **Engagement:** Last.fm plays per listener, Spotify follower/listener conversion,
  YouTube engagement on recent uploads, and Instagram and TikTok engagement
  compared with accounts of the same size
* **Live:** shows and countries in the last 24 months, festival appearances
  weighted by festival tier and billing, upcoming shows, Bandsintown trackers, and
  optional manually entered hard-ticket sales
* **Momentum:** 30-day growth in streaming and social audiences (built from your
  own refresh history) and the Wikipedia attention trend
* **Social footprint:** Instagram, TikTok, SoundCloud and X followers

The weighting rationale and its sources are in
**[docs/research/metric-weights.md](docs/research/metric-weights.md)**.

## Quick start

Requires Python 3.11+.

```bash
git clone https://github.com/snowcrab22/artist-market-data-researcher.git
cd artist-market-data-researcher
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install .
artistscore serve --open        # http://127.0.0.1:8000
```

Or run it with Docker:

```bash
cp .env.example .env            # optional: add keys here, or later in the Settings page
docker compose up -d            # http://127.0.0.1:8000, data kept in ./data
```

Then search for an artist, pick the right match (MusicBrainz shows a short
description for artists that share a name), and the report fills in within about
20 seconds.

To explore the app before adding any keys, run `artistscore demo`. It adds three
clearly labelled **synthetic** artists.

### API keys (all free)

The app works without keys, using MusicBrainz, Wikidata, Deezer, Wikipedia and
public pages, but coverage is much better with them. Paste keys into
**Settings** in the app, or put them in `.env`:

| Key | Unlocks | Get it |
|---|---|---|
| `LASTFM_API_KEY` | listeners, plays and plays per listener (engagement) | https://www.last.fm/api/account/create |
| `YOUTUBE_API_KEY` | subscribers, views, engagement rate | Google Cloud console → YouTube Data API v3 |
| `SETLISTFM_API_KEY` | show history, countries, festival sets | https://www.setlist.fm/settings/api (non-commercial) |
| `TICKETMASTER_API_KEY` | upcoming shows, festival bookings | https://developer.ticketmaster.com/ |
| `BANDSINTOWN_APP_ID` | trackers, upcoming shows | issued by Bandsintown on request |
| `SPOTIFY_CLIENT_ID` / `_SECRET` | artist ID lookup (optional) | https://developer.spotify.com/dashboard |
| `CONTACT_EMAIL` | identifies you to MusicBrainz, as its API rules ask | — |

Run `artistscore doctor` to see which keys are set and whether each platform
can be reached from your network.

## How the score works (short version)

1. **Normalise.** Audience counts follow a power law, so each is placed on a log
   scale between "barely started" and "global superstar" anchors. For example,
   Spotify monthly listeners run from 1K = 0 to 50M = 100. Engagement rates are
   compared with the benchmark for the account's size, and growth is mapped
   around 50 = flat.
2. **Weight.** There are four level pillars: **live 30**, **reach 25**,
   **engagement 20** and **social 10**. **Momentum** (weight 15) then moves the
   result up or down by at most ±7.5 points. Live demand carries the most weight
   because promoters pay for ticket buyers, and festival billing is an outside,
   paid valuation of the artist. Raw follower counts carry the least weight
   because they are easy to inflate and predict ticket sales poorly.
3. **Handle gaps honestly.** A metric without data gives its weight to the other
   metrics in its pillar. **Coverage** shows how much of the model was actually
   measured, as high, medium or low confidence.
4. **Assign a tier.** ≥75 Superstar / headliner, ≥60 Established, ≥45 Mid-level,
   ≥30 Developing, otherwise Emerging.

You can edit every weight on the **Weights** page. Saving re-scores all artists
from stored data without re-fetching anything.

## Features

* **Artist report:** the score, pillar bars, each metric with its value, score,
  share of the total and source, plus festival appearances, recent and upcoming
  shows, the status of each source, and score history.
* **Manual values:** enter numbers that have no free source, such as average
  hard-ticket sales from Pollstar or your own settlements, or numbers from a
  platform that blocked access. Manual values override fetched ones and are
  labelled "manual".
* **Platform links:** found automatically from MusicBrainz and Wikidata. You can
  edit any of them, and pasting a full profile URL works.
* **Compare:** artists side by side, metric by metric.
* **Export:** `/export.csv` for all artists, `/artist/{id}.json` for one.
* **CLI:** `artistscore score "Artist Name" [--mbid …] [--json]`,
  `artistscore search NAME`, `artistscore doctor`, `artistscore demo`.

To share it on your local network, run `artistscore serve --host 0.0.0.0`, or
change the port mapping in `docker-compose.yml`. There is no login, so only do
this on a network you trust.

## Design decision: no agent in the loop

Every step is deterministic. Platform IDs come from MusicBrainz and Wikidata
links, metrics come from APIs and public pages, and the score is a fixed,
documented formula. The only step that needs judgement is choosing between artists
who share a name, and the user does that in the search screen. An LLM in the loop
would add cost and an API dependency, and the same artist could get a different
score on each run, with no gain in accuracy. Scrapers that break are handled with
manual values, not with an agent.

## Limitations and fair use

* **Spotify:** monthly listeners are read from the public artist page. In
  February 2026 Spotify removed followers and popularity from the Web API for
  development-mode apps, and monthly listeners were never in the API.
* **Instagram, TikTok, SoundCloud and the Spotify page** are read from public
  pages on a best-effort basis. These platforms often block automated requests
  and change their page layouts. When a source fails, the app says so and you can
  enter the number by hand. Check each platform's terms before automated use. Any
  source can be disabled with `DISABLED_SOURCES`.
* **No public source has ticket sales or venue capacities.** The live pillar
  relies on proxies (show volume, festival tier, trackers) unless you enter
  `avg_ticket_sales`.
* **Festival detection** matches MusicBrainz, setlist.fm and Ticketmaster event
  data against a catalog of about 90 festivals (`artistscore/festivals.yaml`;
  extend it freely). Headliner billing is only known when MusicBrainz records it.
* **setlist.fm's API is free for non-commercial use only.**
* The parsers are tested against recorded response shapes. Platforms change
  without notice, so run `artistscore doctor` and check each source's status on
  the artist page.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Layout: `artistscore/sources/` holds one module per platform, each with
`async fetch(ctx) -> SourceResult`. `artistscore/scoring/` holds the pure scoring
engine and `weights.yaml`. `service.py` orchestrates refreshes and reports,
`web/` is the FastAPI and Jinja2 UI, and `storage.py` is the SQLite layer. Design
notes are in `docs/superpowers/`.

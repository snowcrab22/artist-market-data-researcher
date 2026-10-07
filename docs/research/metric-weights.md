# Metric research and weighting rationale

This document explains **why** ArtistScore weighs metrics the way it does. The
weights live in `artistscore/scoring/weights.yaml` and can be changed in the UI
(`/weights`); this file is the reasoning behind the defaults.

Research date: October 2026.

## 1. What the score is trying to measure

The goal is a single number for an artist's **relative market value**: how
much audience, fan commitment and live pull the artist has, compared with other
artists. The main consumer of that judgement in practice is someone booking,
signing or investing in an artist. So the guiding question is the
promoter's: *"How many tickets can this artist sell, and how durable is that
demand?"* ([artist.tools](https://www.artist.tools/post/what-do-promoters-do-in-the-music-industry)).

## 2. What the industry does

| Source | What it tells us |
|---|---|
| **Chartmetric Artist Score / CPP** ([Hypebot summary](https://www.hypebot.com/chartmetric-originals-cross-platform-performance-cpp-ranks-and-scores-1/), [API docs](https://apidocs.chartmetric.com/reference/tag/artist/get/api/artist/id/cpp)) | The score is two sub-scores: *Stage* (reach, meaning how many people actively consume) and *Followers* (fanbase stickiness). The weighted average "heavily prioritizes Stage over Followers". Each platform is scaled from smallest to largest artist, there is a small bonus for being present on more platforms, and Fan Base and Engagement sub-ranks were added later. |
| **Soundcharts Artist Score** ([help center](https://help.soundcharts.com/en/articles/10450174-how-are-soundcharts-scores-and-career-stages-calculated)) | The score is a weighted average of a *Fanbase* score (total following across platforms) and a *Trending* score (7-day growth, including Spotify monthly listeners), rescaled **logarithmically**. Career stages are percentiles: Superstar is the top 0.03%, Mainstream the next 0.2%, Developing the next 1%, and Long-tail the rest. |
| **Pollstar 2024 "Deep Data Cuts" part 4** ([Pollstar](https://news.pollstar.com/2025/02/07/below-pollstars-top-100-tours-part-4-media-presence-sabrina-carpenter-benson-boone-teddy-swims-and-kendrick-lamar-dominate-popularity-growth-deep-data-cuts/)) | For artists below the Top 100 tours, year-over-year ticket sales were **most sensitive to social-media growth**, then streaming growth, then airplay. The input is *growth*, not raw follower counts. |
| **Booking practice** ([Opendate / Lefsetz](https://www.opendate.io/post/bob-lefsetz-on-bridging-the-gap-between-streaming-stats-and-ticket-sales), [Opendate](https://opendate.io/post/evaluating-talent-dig-deeper-to-uncover-the-full-story), ["1M monthly listeners, 12 tickets"](https://joelgouveia.substack.com/p/1-million-monthly-listeners-12-tickets), [Prism](https://prism.fm/blog/insights/what-analytics-matter-most-for-booking-and-talent-agencies/)) | Local ticket history and live demand matter most. Streaming numbers are "one piece of the puzzle" and can come from playlists or sync placements that never convert into ticket buyers. |
| **Listener-to-fan conversion** ([Orphiq](https://orphiq.com/resources/spotify-analytics-tour-routing), [Chartmetric follower ratio via Hypebot](https://www.hypebot.com/using-spotify-follower-ratio-to-measure-artist-growth-and-fan-engagement/), [Chartmetric help](https://help.chartmetric.com/en/articles/4382245-can-you-explain-the-spotify-fan-conversion-rate)) | Vendor rules of thumb put ticket conversion at 0.5–1% for casual playlist listeners, 2–3% for engaged followers, 3–5% for dedicated fans and 5–10% for superfans. An engaged fan is therefore worth roughly 3–5 passive listeners. Followers ÷ monthly listeners is the standard "conversion" proxy. It is U-shaped across career stage, so it gets moderate weight only. |
| **Festival economics** ([FestivalPro](https://festivalpro.com/festival-management/4516/news/2025/12/8/Managing-Artist-Fee-Budgets-in-the-Music-Festival-Curation-Process.html), [IQ Mag on Roskilde billing](https://www.iq-mag.net/2019/09/iff-the-big-billing-debate/), [Vice](https://broadly.vice.com/en/article/7xnk9z/festival-lineup-order-names-font-size-booking), [TSE white paper](https://tseentertainment.com/white-paper/the-2026-fair-festival-lineup-playbook/)) | Headliners take about 40% of a festival's talent budget. Billing tiers are explicit (Roskilde font sizes are 100/90/70/50/40%), and an act's billing at one festival carries over to its next fee negotiation. Festival bookings are a **paid, third-party valuation** of the artist, which makes them the strongest public signal of fee level. |
| **Wikipedia attention** ([Next Big Sound via Hypebot](https://www.hypebot.com/data-science-and-the-music-industry-what-social-media-has-to-do-with-record-sales/)) | Wikipedia pageviews correlated with album sales better than tweets or Facebook likes did. It is a cheap, hard-to-fake awareness signal. |
| **Last.fm plays per listener** ([Online Fandom](https://www.onlinefandom.com/archives/using-lastfm-to-measure-fan-devotion/)) | Plays ÷ listeners is an established "devotion" measure. Typical values run from about 4 (casual) to over 100 (The Beatles). It is biased towards catalog acts because the totals are lifetime. |
| **Social engagement benchmarks** ([Emplicit / Influencer Marketing Factory](https://emplicit.co/tiktok-engagement-rate-benchmarks-2025/), [iqfluence](https://iqfluence.io/public/blog/social-media-benchmarks), [Archive](https://archive.com/blog/good-influencer-engagement-rate-tier), [Socialinsider music](https://www.socialinsider.io/social-media-benchmarks/music-performance-arts)) | Engagement rate **falls as accounts grow**. On TikTok it runs from about 7.5% under 100K followers to about 2.9% above 10M. On Instagram it runs from 2.5–4% for nano accounts to 0.3–0.5% for mega accounts. Raw rates are not comparable across sizes, so we score the **ratio against the expected rate for the account's size tier**. |

### Data-availability constraints that shape the model

* **Spotify Web API (February/March 2026):** artist `followers` and `popularity`
  were removed from Development-Mode apps
  ([Spotify changelog](https://developer.spotify.com/documentation/web-api/references/changes/february-2026),
  [migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)).
  Monthly listeners were never in the API. We therefore read monthly listeners
  (and followers, when present) from the public artist page, and use the API
  only when the user has credentials that still return those fields.
* **Ticket sales / venue capacity** are not publicly available. Pollstar and
  Chartmetric data are paid. The model accepts **manual entry** of average
  hard-ticket sales, and gives it the highest weight in the live pillar when
  present.
* **Instagram / TikTok / X** have no free public APIs. Public-page parsing is
  best-effort and often blocked, so every social metric can also be entered
  manually.
* **setlist.fm** (free, non-commercial key) is the best public show history.
  **MusicBrainz** events (no key) list festivals with event type `Festival`.

## 3. The model

### 3.1 Normalisation

Audience sizes are power-law distributed, so every count metric is scored on a
**log scale between two anchors** (as Soundcharts does):

```
score = 100 × clamp( (log10(x) − log10(lo)) / (log10(hi) − log10(lo)), 0, 1 )
```

The anchors are set so that `lo` is a "barely started" act and `hi` is
global-superstar territory. For example, 50M Spotify monthly listeners scores
100, 5M scores 79, 500K scores 57, 50K scores 36 and 1K scores 0.

The other metric types are scored as follows:

* **Engagement rates vs. size tier:** `score = 50 + 25·log2(actual / expected)`,
  clamped to 0–100. Hitting the benchmark for your size scores 50, doing 4×
  better scores 100, and doing 4× worse scores 0.
* **Growth:** `score = 50 + 50·clamp(ln(1+g) / ln(1+full))`, where `g` is the
  growth rate normalised to 30 days. Flat scores 50, `+full` scores 100 and the
  symmetric decline scores 0.
* **Ratios** (follower/listener, plays/listener): the same log scale with
  anchors taken from the published ranges.

### 3.2 Pillars and default weights

| Pillar | Weight | Why |
|---|---:|---|
| **Live demand & track record** | **30** | Ticket-buying fans are what promoters pay for. Festival billing is an outside, money-backed valuation, and show volume and geographic spread show proven touring demand. This pillar is the hardest to fake. |
| **Audience reach** | **25** | Matches Chartmetric's "Stage" emphasis and is the most-cited industry currency, but it is capped below live because reach alone converts poorly (the "1M listeners, 12 tickets" problem). |
| **Fan engagement & loyalty** | **20** | Separates committed fans from passive playlist listeners. Conversion benchmarks suggest an engaged fan is worth 3–5× a passive listener, and Chartmetric and Soundcharts both added engagement and fanbase sub-scores. |
| **Momentum** | **15** (± adjustment) | Soundcharts' Trending score, plus Pollstar's finding that ticket sales are most sensitive to social growth. It is applied as an **adjustment** rather than averaged in (see below), because growth is noisy and needs history snapshots to compute. |
| **Social footprint** | **10** | Raw follower counts are easy to inflate and weakly predictive (Pollstar found *growth*, not size, mattered). They still show addressable marketing reach, and their growth is counted under Momentum. |

**Why momentum is an adjustment, not a level pillar.** Growth scores are centred on
50, where 50 means flat. Averaging momentum into the other pillars would pull every
stable artist towards the middle: a flat-growing stadium act would lose about 6
points to the averaging alone. Soundcharts keeps *Fanbase* (level) and
*Trending* (change) as separate sub-scores for the same reason. ArtistScore
therefore averages the four level pillars (live, reach, engagement, social,
renormalised over 85), then **shifts** the total by
`(15/100) × (momentum − 50)`. Flat growth changes nothing, and strong growth or
decline moves the score by at most ±7.5 points. Calibration check with the
synthetic demo profiles: a 28M-listener festival headliner scores 81, a
650K-listener touring band 58, and a viral act with 3.2M listeners but six shows
42.

### 3.3 Metrics within each pillar

Weights within a pillar are **relative**. They are renormalised over the
metrics that are actually available for an artist (see 3.4).

**Live (30)**

| Metric | Weight | Scale | Source |
|---|---:|---|---|
| `avg_ticket_sales` (manual) | 40 | log 50 → 50,000 | Manual entry (Pollstar / own data) |
| `festival_score` | 35 | log 1 → 200 | MusicBrainz events + setlist.fm + Ticketmaster, matched against the festival tier catalog |
| `shows_24mo` | 25 | log 2 → 200 | setlist.fm, falling back to MusicBrainz / Bandsintown |
| `bandsintown_trackers` | 20 | log 500 → 10M | Bandsintown |
| `countries_24mo` | 10 | log 1 → 40 | setlist.fm |
| `upcoming_shows` | 10 | log 1 → 100 | Ticketmaster / Bandsintown |

`festival_score` sums points for each festival appearance, decayed with a
two-year half-life. A tier-1 festival is worth 10 points (20 as headliner), a
tier-2 festival 5 (10 as headliner), and any other festival 2 (3 as headliner).
The tier catalog (`artistscore/festivals.yaml`) follows the billing and budget
hierarchy described above: global flagship festivals are tier 1, and major
national and genre flagships are tier 2.

**Reach (25)**

| Metric | Weight | Scale |
|---|---:|---|
| `spotify_monthly_listeners` | 35 | log 1K → 50M |
| `lastfm_listeners` | 15 | log 1K → 5M |
| `youtube_subscribers` | 10 | log 1K → 50M |
| `youtube_views` | 10 | log 100K → 20B |
| `deezer_fans` | 10 | log 500 → 20M |
| `wikipedia_monthly_views` | 10 | log 500 → 2M |
| `spotify_followers` | 10 | log 1K → 100M |

Spotify is the dominant streaming platform and the industry's default reach
currency, so it carries the most weight. Last.fm counts unique *scrobbling*
listeners, which are self-selected engaged listeners and hard to inflate.

**Engagement (20)**

| Metric | Weight | Scale |
|---|---:|---|
| `lastfm_plays_per_listener` | 30 | log 3 → 80 |
| `spotify_follower_ratio` (followers ÷ monthly listeners) | 20 | log 0.05 → 2.0 |
| `youtube_engagement_rate` ((likes+comments) ÷ views, last 10 uploads) | 20 | log 0.3% → 10% |
| `instagram_engagement_rate` | 15 | vs. size-tier benchmark |
| `tiktok_engagement_rate` (avg likes per video ÷ followers) | 15 | vs. size-tier benchmark |

**Momentum (15)**

| Metric | Weight | Scale |
|---|---:|---|
| `social_growth_30d` (mean growth of IG, TikTok and YouTube followers) | 40 | growth, +25%/mo = 100 |
| `streaming_growth_30d` (mean growth of Spotify ML, Deezer fans and Last.fm listeners) | 35 | growth, +25%/mo = 100 |
| `wikipedia_trend` (last 3 months vs. prior 9) | 25 | growth, 2× = 100 |

The growth metrics need at least two snapshots 14 or more days apart, so they
appear after the second refresh. `wikipedia_trend` is available on the first
run.

**Social (10)**

| Metric | Weight | Scale |
|---|---:|---|
| `instagram_followers` | 40 | log 1K → 100M |
| `tiktok_followers` | 35 | log 1K → 50M |
| `x_followers` (manual) | 15 | log 1K → 50M |
| `soundcloud_followers` | 10 | log 200 → 5M |

### 3.4 Missing data and confidence

Free sources never cover every artist. When a metric is missing:

1. Its weight is redistributed across the other metrics in the same pillar.
2. If a whole pillar is empty, its weight is redistributed across the other
   pillars.
3. **Coverage** is the share of the default model weight that was actually
   measured. It is reported next to the score, with confidence labelled
   *high* (≥ 70%), *medium* (≥ 40%) or *low*.

A score of 72 at 35% coverage should be read as "probably strong, but unverified".

### 3.5 Tiers

These labels follow the spirit of Soundcharts' career stages, where "Superstar"
is the top 0.03% of artists, roughly the top 4,500. The cut-offs were calibrated
on reference profiles:

| Score | Tier | Typical profile |
|---|---|---|
| ≥ 75 | Superstar / headliner | 10M+ monthly listeners, tier-1 festival headline slots |
| 60–75 | Established | 1–5M listeners, theatres and arenas, festival mid-card |
| 45–60 | Mid-level | 200K–1M listeners, club and theatre touring, tier-2 festivals |
| 30–45 | Developing | 20K–200K listeners, or reach without live history |
| < 30 | Emerging | early-career acts |

## 4. Known limitations

* There is no public ticket-sales or venue-capacity data. The live pillar uses
  proxies unless `avg_ticket_sales` is entered manually.
* Festival detection depends on MusicBrainz and setlist.fm data entry and on
  catalog name matching. Billing position (headliner or not) is only known when
  MusicBrainz records it.
* Lifetime Last.fm totals favour catalog acts, and the follower/listener ratio
  is U-shaped across career stage. Both carry only moderate weight for that
  reason.
* The anchors are judgement calls calibrated against well-known artists, not a
  fitted regression. With a labelled dataset (for example, artists with known
  fees), the weights could be fitted. The weights file makes that a
  config-only change.

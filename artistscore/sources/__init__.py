"""Data sources. Each module exposes NAME, LABEL, REQUIRES (setting keys) and `async fetch(ctx)`."""

from artistscore.sources import (bandsintown, deezer, instagram, lastfm, musicbrainz_events, setlistfm, soundcloud,
                                 spotify, spotify_api, ticketmaster, tiktok, wikipedia, youtube)

ALL_SOURCES = [spotify, spotify_api, deezer, lastfm, youtube, wikipedia, musicbrainz_events, setlistfm,
               ticketmaster, bandsintown, instagram, tiktok, soundcloud]

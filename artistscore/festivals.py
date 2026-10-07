"""Festival recognition and the tier-weighted, recency-decayed festival_score."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from artistscore.models import FestivalAppearance

CATALOG_PATH = Path(__file__).with_name("festivals.yaml")

# points per appearance: tier -> (regular, headliner)
POINTS = {1: (10.0, 20.0), 2: (5.0, 10.0), 3: (2.0, 3.0)}
HALF_LIFE_YEARS = 2.0
WINDOW_YEARS = 5.0

GENERIC = re.compile(r"\b(festival|festivals|fest|festivalen|festiwal|open air|openair)\b")
# Permanent venues named after festivals ("Royal Festival Hall") are not festivals.
TRAILING_YEAR = re.compile(r"[\s\-–,]*\b(19|20)\d{2}\b\s*$")
VENUE_WORDS = re.compile(r"\bfestival (hall|theatre|theater|centre|center|house|arena|pavilion|ballroom|plaza|square)\b")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


@lru_cache(maxsize=1)
def _catalog() -> list[tuple[str, int, re.Pattern[str]]]:
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    entries = []
    for fest in data["festivals"]:
        terms = [normalise(t) for t in fest.get("aliases", []) + fest.get("venues", [])]
        pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b")
        entries.append((fest["name"], int(fest["tier"]), pattern))
    return entries


def match_festival(*texts: str | None) -> tuple[str, int] | None:
    """Recognise a festival from event name / venue / tour texts. Returns (name, tier) or None."""
    present = [t for t in texts if t]
    for text in present:
        norm = normalise(text)
        for name, tier, pattern in _catalog():
            if pattern.search(norm):
                return name, tier
    for text in present:
        norm = normalise(text)
        if GENERIC.search(norm) and not VENUE_WORDS.search(norm):
            return TRAILING_YEAR.sub("", text).strip() or text.strip(), 3
    return None


def festival_score(appearances: list[FestivalAppearance], today: date) -> float:
    total = 0.0
    for app in appearances:
        years_ago = max(0.0, (today - app.date).days / 365.25)
        if years_ago > WINDOW_YEARS:
            continue
        regular, headliner = POINTS.get(app.tier, POINTS[3])
        points = headliner if app.role == "headliner" else regular
        total += points * 0.5 ** (years_ago / HALF_LIFE_YEARS)
    return total


def dedupe(appearances: list[FestivalAppearance]) -> list[FestivalAppearance]:
    """One appearance per festival per year, preferring a record that knows the artist headlined."""
    best: dict[tuple[str, int], FestivalAppearance] = {}
    for app in appearances:
        key = (normalise(app.name), app.date.year)
        current = best.get(key)
        if current is None or (app.role == "headliner" and current.role != "headliner"):
            best[key] = app
    return sorted(best.values(), key=lambda a: a.date, reverse=True)

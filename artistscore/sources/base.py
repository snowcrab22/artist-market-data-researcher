"""Shared source plumbing: the context passed to every source and number parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from types import ModuleType

import httpx

from artistscore.config import Settings
from artistscore.models import ArtistLinks, SourceResult

SUFFIXES = {"k": 1e3, "m": 1e6, "b": 1e9}


@dataclass
class SourceContext:
    name: str
    links: ArtistLinks
    settings: Settings
    client: httpx.AsyncClient
    today: date


class SourceError(Exception):
    """A source-specific failure with a message fit to show the user."""


def parse_count(text: str | None) -> float | None:
    """Parse "11.6M", "12,345", "1 234", "2.5K" into a number."""
    if not text:
        return None
    cleaned = text.strip().replace(" ", "").replace(" ", "").replace(" ", "")
    match = re.fullmatch(r"([\d.,]+)([kmbKMB]?)", cleaned)
    if not match:
        return None
    digits, suffix = match.groups()
    if suffix:
        if "," in digits and "." not in digits:
            digits = digits.replace(",", ".")  # "1,2M" (European decimal comma)
        digits = digits.replace(",", "")
    else:
        digits = digits.replace(",", "").replace(".", "") if re.fullmatch(r"\d{1,3}([.,]\d{3})+", digits) else digits
    try:
        value = float(digits)
    except ValueError:
        return None
    return value * SUFFIXES.get(suffix.lower(), 1) if suffix else value


def parse_partial_date(text: str | None) -> date | None:
    """Parse "2024-07-12", "2024-07" or "2024" (MusicBrainz style)."""
    if not text:
        return None
    parts = [int(p) for p in text.split("-") if p.isdigit()]
    try:
        return date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except (IndexError, ValueError):
        return None


def months_ago(today: date, months: int) -> date:
    year, month = divmod(today.year * 12 + today.month - 1 - months, 12)
    day = min(today.day, 28)
    return date(year, month + 1, day)


async def run_source(module: ModuleType, ctx: SourceContext) -> SourceResult:
    """Run one source, converting every failure into a SourceResult with status "error"."""
    name = module.NAME
    try:
        return await module.fetch(ctx)
    except SourceError as exc:
        return SourceResult.failed(name, str(exc))
    except httpx.HTTPStatusError as exc:
        return SourceResult.failed(name, f"HTTP {exc.response.status_code} from {exc.request.url.host}")
    except httpx.RequestError as exc:
        return SourceResult.failed(name, f"network error: {type(exc).__name__}: {exc}")
    except Exception as exc:  # parsers meet unexpected page/API shapes; never fail the refresh
        return SourceResult.failed(name, f"unexpected response: {type(exc).__name__}: {exc}")

"""Plain data types shared by sources, storage, scoring and the web layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date
from typing import Any


@dataclass
class Metric:
    key: str
    value: float
    source: str
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Metric":
        return cls(data["key"], float(data["value"]), data.get("source", ""), data.get("note"))


@dataclass
class SourceResult:
    source: str
    status: str  # "ok" | "skipped" | "error"
    metrics: dict[str, Metric] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def ok(cls, source: str, metrics: list[Metric], details: dict[str, Any] | None = None) -> "SourceResult":
        return cls(source, "ok", {m.key: m for m in metrics}, details or {})

    @classmethod
    def skipped(cls, source: str, reason: str) -> "SourceResult":
        return cls(source, "skipped", error=reason)

    @classmethod
    def failed(cls, source: str, reason: str) -> "SourceResult":
        return cls(source, "error", error=reason)


@dataclass
class ArtistLinks:
    mbid: str | None = None
    spotify_id: str | None = None
    youtube_channel_id: str | None = None
    youtube_handle: str | None = None
    instagram: str | None = None
    tiktok: str | None = None
    soundcloud: str | None = None
    twitter: str | None = None
    deezer_id: str | None = None
    lastfm_name: str | None = None
    wikipedia_title: str | None = None
    wikidata_id: str | None = None
    bandsintown_name: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ArtistLinks":
        names = {f.name for f in fields(cls)}
        return cls(**{k: (v or None) for k, v in (data or {}).items() if k in names})

    @classmethod
    def field_names(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    def fill_missing(self, other: "ArtistLinks") -> None:
        """Copy values from `other` into fields that are still empty."""
        for name in self.field_names():
            if not getattr(self, name) and getattr(other, name):
                setattr(self, name, getattr(other, name))


@dataclass
class FestivalAppearance:
    name: str
    tier: int
    date: date
    role: str | None = None  # "headliner" when known
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "tier": self.tier, "date": self.date.isoformat(),
                "role": self.role, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FestivalAppearance":
        return cls(data["name"], int(data["tier"]), date.fromisoformat(data["date"]),
                   data.get("role"), data.get("source", ""))

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from artistscore import http as ahttp
from artistscore.config import KEYS, Settings
from artistscore.models import ArtistLinks
from artistscore.sources.base import SourceContext

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 7)


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


@pytest.fixture(autouse=True)
def _fast_http(monkeypatch):
    monkeypatch.setattr(ahttp, "HOST_INTERVALS", {})
    monkeypatch.setattr(ahttp, "RETRY_BACKOFF", 0.0)
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)


class DictSettings(Settings):
    def __init__(self, values=None):
        super().__init__(None)
        self.values = values or {}

    def get(self, key):
        return self.values.get(key)


@pytest.fixture
def make_ctx():
    clients = []

    def _make(name="Test Artist", settings=None, **links):
        client = httpx.AsyncClient()
        clients.append(client)
        return SourceContext(name=name, links=ArtistLinks(**links), settings=DictSettings(settings),
                             client=client, today=TODAY)

    yield _make

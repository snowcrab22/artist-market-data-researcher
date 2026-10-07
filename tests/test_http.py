import httpx
import pytest
import respx

from artistscore import http


@respx.mock
async def test_retries_once_on_503_then_succeeds():
    route = respx.get("https://api.example.org/x").mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    async with httpx.AsyncClient() as client:
        assert await http.get_json(client, "https://api.example.org/x") == {"ok": 1}
    assert route.call_count == 2


@respx.mock
async def test_gives_up_after_one_retry():
    respx.get("https://api.example.org/x").respond(429)
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await http.get(client, "https://api.example.org/x")


@respx.mock
async def test_404_is_not_retried():
    route = respx.get("https://api.example.org/x").respond(404)
    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await http.get(client, "https://api.example.org/x")
    assert route.call_count == 1

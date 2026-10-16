"""The service pings its own public /health so Render's free plan never idles it out."""

import asyncio

import httpx
import pytest

from app.core import keep_awake


def test_target_url_only_on_render_and_can_be_switched_off(monkeypatch):
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.delenv("KEEP_AWAKE_URL", raising=False)
    monkeypatch.delenv("KEEP_AWAKE", raising=False)
    assert keep_awake.target_url() is None  # local development: nothing to keep awake
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://api.example.onrender.com/")
    assert keep_awake.target_url() == "https://api.example.onrender.com/health"
    monkeypatch.setenv("KEEP_AWAKE", "false")
    assert keep_awake.target_url() is None


async def test_loop_keeps_calling_health(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200 if len(calls) != 2 else 503)  # one failure must not stop the loop

    real_client = httpx.AsyncClient
    monkeypatch.setattr(keep_awake.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    task = asyncio.create_task(keep_awake.keep_awake_loop("https://api.example.onrender.com/health", interval=0.01))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) >= 3 and set(calls) == {"https://api.example.onrender.com/health"}

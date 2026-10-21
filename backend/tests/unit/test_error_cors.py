"""A crashing endpoint still answers with CORS headers, so the browser can read the JSON 500."""

from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_unhandled_error_keeps_cors_headers():
    app = create_app()

    @app.get("/__boom")
    async def boom() -> dict:
        raise RuntimeError("database is down")

    origin = "http://localhost:5173"
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t") as client:
        r = await client.get("/__boom", headers={"Origin": origin})
        assert r.status_code == 500
        assert r.headers.get("access-control-allow-origin") == origin
        assert r.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

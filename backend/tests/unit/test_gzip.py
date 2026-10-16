"""Large API replies are gzip-compressed when the browser accepts it; small ones are not."""

from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_large_json_is_compressed_small_is_not():
    app = create_app()

    @app.get("/__big")
    async def big() -> dict:
        return {"items": [{"id": i, "name": f"game-{i}"} for i in range(400)]}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        r = await client.get("/__big", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip" and len(r.json()["items"]) == 400
        small = await client.get("/health", headers={"Accept-Encoding": "gzip"})
        assert small.headers.get("content-encoding") != "gzip"

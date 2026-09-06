"""Tests for enforced limits and the intentional health-check exemption."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.rate_limit import RateLimitMiddleware, _buckets, settings


async def test_rate_limit_rejects_excess_traffic(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_rpm", 2)
    _buckets.clear()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/limited")
    async def limited():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/limited")).status_code == 200
        assert (await client.get("/limited")).status_code == 200
        response = await client.get("/limited")
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0
    _buckets.clear()


async def test_health_check_is_exempt_from_rate_limiting(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_rpm", 0)
    for _ in range(5):
        response = await client.get("/health")
        assert response.status_code == 200

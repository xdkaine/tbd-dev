"""Tests for the rate limiting middleware."""

import asyncio


async def test_rate_limit_allows_normal_traffic(client):
    """Normal request volume should pass through without 429."""
    # Health endpoint is lightweight — send a few requests
    for _ in range(5):
        resp = await client.get("/health")
        assert resp.status_code == 200


async def test_rate_limit_headers_present(client):
    """Responses should include X-RateLimit headers."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    # Our middleware sets these headers
    assert "x-ratelimit-limit" in resp.headers
    assert "x-ratelimit-remaining" in resp.headers

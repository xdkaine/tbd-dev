"""Tests for health and root endpoints."""


async def test_health_endpoint(client):
    """GET /health returns status ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "tbd-api"


async def test_root_endpoint(client):
    """GET / returns API info."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "TBD Platform API"
    assert "docs" in data

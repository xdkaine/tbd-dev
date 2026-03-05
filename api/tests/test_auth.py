"""Tests for authentication endpoints."""

import uuid


async def test_get_me_unauthenticated(client):
    """GET /auth/me without token should return 401 or 403."""
    resp = await client.get("/auth/me")
    assert resp.status_code in (401, 403)


async def test_get_me_with_valid_token(client, create_user, auth_headers):
    """GET /auth/me with a valid JWT returns user info."""
    user = await create_user(
        username="jdoe",
        display_name="Jane Doe",
        email="jdoe@sdc.cpp",
    )

    headers = auth_headers(user_id=user.id, username="jdoe", role="JAS_Developer")
    resp = await client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "jdoe"
    assert data["display_name"] == "Jane Doe"
    assert data["role"] == "JAS_Developer"


async def test_get_me_deleted_user(client, make_token):
    """GET /auth/me with token for non-existent user returns 401."""
    fake_id = uuid.uuid4()
    token = make_token(user_id=fake_id, username="ghost")
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_get_me_invalid_token(client):
    """GET /auth/me with a garbage token returns 401 or 403."""
    resp = await client.get(
        "/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"}
    )
    assert resp.status_code in (401, 403)


async def test_login_invalid_credentials(client):
    """POST /auth/login with invalid credentials returns 401.

    Note: This test relies on AD not being available, so the AD auth
    service should return None, resulting in 401.
    """
    resp = await client.post(
        "/auth/login",
        json={"username": "nobody", "password": "wrong"},
    )
    # Without a real AD server, this should fail at the auth service level
    # Accept either 401 (auth failed) or 500 (AD unreachable)
    assert resp.status_code in (401, 500)


def test_create_access_token():
    """create_access_token returns a valid JWT string and expiry."""
    from app.middleware.auth import create_access_token

    uid = uuid.uuid4()
    token, expires_in = create_access_token(uid, "testuser", "JAS_Developer")
    assert isinstance(token, str)
    assert len(token) > 0
    assert expires_in > 0


def test_jwt_roundtrip():
    """Token created by create_access_token can be decoded back."""
    from jose import jwt as jose_jwt

    from app.config import settings
    from app.middleware.auth import create_access_token

    uid = uuid.uuid4()
    token, _ = create_access_token(uid, "testuser", "JAS-Staff")
    payload = jose_jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm]
    )
    assert payload["sub"] == str(uid)
    assert payload["username"] == "testuser"
    assert payload["role"] == "JAS-Staff"

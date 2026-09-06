import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from app.middleware.auth import (CurrentUser, create_access_token, get_current_user,
                                 get_current_user_from_token, require_current_session)
from app.services import oidc
from app.services.rbac import Role


@pytest.fixture
def strict(monkeypatch):
    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    monkeypatch.setattr(settings, "oidc_issuer", "https://auth.example.com")
    monkeypatch.setattr(settings, "oidc_audience", "tbd-client")
    monkeypatch.setattr(settings, "oidc_client_secret", "test-only")


def session():
    user = SimpleNamespace(id=uuid.uuid4(), username="test", display_name="Test", email="test@example.com")
    token, _ = create_access_token(user.id, user.username, Role.DEVELOPER.value,
                                  application_access=True, source_expires_at=int(time.time()) + 300,
                                  provider_sid="provider-session", provider_sub="test")
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=user))
    return token, db


async def test_logout_then_replay_denied_http_sse_exchange(strict, monkeypatch):
    from app.routers.auth import logout, oidc_exchange
    from app.schemas.auth import OidcExchangeRequest
    active = True
    async def call(path, sid, sub):
        nonlocal active
        assert sid == "provider-session" and sub == "test"
        if path == "backchannel-logout":
            active = False
            return {"destroyed": True}
        return {"active": active}
    monkeypatch.setattr(oidc, "session_request", call)
    token, db = session()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    current = await get_current_user(credentials, db)
    await logout(current)
    for validate in (lambda: get_current_user(credentials, db), lambda: get_current_user_from_token(token, db),
                     lambda: require_current_session(current)):
        with pytest.raises(HTTPException) as exc:
            await validate()
        assert exc.value.status_code == 401
    monkeypatch.setattr(oidc, "verify_id_token", AsyncMock(return_value={"sid": "provider-session", "sub": "test"}))
    db.execute.reset_mock()
    with pytest.raises(HTTPException):
        await oidc_exchange(OidcExchangeRequest(id_token="original-signed-token"), db)
    db.execute.assert_not_called()


@pytest.mark.parametrize("result", [{"active": False}, {"active": "true"}, {}])
async def test_foreign_or_missing_session_denied(strict, monkeypatch, result):
    monkeypatch.setattr(oidc, "session_request", AsyncMock(return_value=result))
    token, db = session()
    with pytest.raises(HTTPException):
        await get_current_user_from_token(token, db)
    db.execute.assert_not_called()


async def test_outage_denies_access_and_logout_reports_failure(strict, monkeypatch):
    from app.routers.auth import logout
    monkeypatch.setattr(oidc, "session_request", AsyncMock(side_effect=oidc.OidcError("offline")))
    token, db = session()
    with pytest.raises(HTTPException):
        await get_current_user_from_token(token, db)
    current = CurrentUser(uuid.uuid4(), "test", "Test", "test@example.com", Role.DEVELOPER,
                          "provider-session", "test", int(time.time()) + 10)
    with pytest.raises(HTTPException) as exc:
        await logout(current)
    assert exc.value.status_code == 503


async def test_expired_stream_fails_before_provider_check(strict, monkeypatch):
    check = AsyncMock()
    monkeypatch.setattr(oidc, "require_active_session", check)
    current = CurrentUser(uuid.uuid4(), "test", "Test", "test@example.com", Role.DEVELOPER,
                          "provider-session", "test", int(time.time()) - 1)
    with pytest.raises(HTTPException):
        await require_current_session(current)
    check.assert_not_called()


async def test_github_state_bound_to_provider_and_original_expiry(strict):
    from app.routers.auth import _create_oauth_state
    from jose import jwt
    current = CurrentUser(uuid.uuid4(), "test", "Test", "test@example.com", Role.DEVELOPER,
                          "provider-session", "test", int(time.time()) + 30)
    claims = jwt.decode(_create_oauth_state(str(current.id), current), settings.secret_key,
                        algorithms=[settings.jwt_algorithm])
    assert claims["provider_sid"] == "provider-session"
    assert claims["provider_sub"] == "test"
    assert claims["exp"] == current.expires_at


async def test_missing_credentials_or_sid_fail_closed(strict, monkeypatch):
    with pytest.raises(oidc.OidcError):
        await oidc.require_active_session(None, "test")
    monkeypatch.setattr(settings, "oidc_client_secret", "")
    with pytest.raises(oidc.OidcError):
        await oidc.require_active_session("provider-session", "test")


async def test_status_transport_authenticates_client_and_does_not_cache(strict, monkeypatch):
    import httpx
    calls = []
    async def handler(request):
        calls.append(request)
        assert request.url == "https://auth.example.com/session/status"
        assert request.headers["authorization"].startswith("Basic ")
        assert b"sid=provider-session" in request.content and b"sub=test" in request.content
        return httpx.Response(200, json={"active": len(calls) == 1})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    await oidc.require_active_session("provider-session", "test")
    with pytest.raises(oidc.OidcError):
        await oidc.require_active_session("provider-session", "test")
    assert len(calls) == 2


async def test_open_build_stream_stops_after_revocation(strict, monkeypatch):
    from app.routers import builds
    current = CurrentUser(uuid.uuid4(), "test", "Test", "test@example.com", Role.FACULTY,
                          "provider-session", "test", int(time.time()) + 60)
    build = SimpleNamespace(logs="first", status="running")
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=build))
    monkeypatch.setattr(oidc, "session_request", AsyncMock(side_effect=[{"active": True}, {"active": False}]))
    response = await builds.stream_build_logs(uuid.uuid4(), uuid.uuid4(), current, db)
    iterator = response.body_iterator
    assert "first" in await anext(iterator)
    build.logs = "first and secret after revoke"
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)
    assert db.refresh.await_count == 1


async def test_logout_already_terminated_is_idempotent(strict, monkeypatch):
    from app.routers.auth import logout
    monkeypatch.setattr(oidc, "session_request", AsyncMock(return_value={"destroyed": False}))
    current = CurrentUser(uuid.uuid4(), "test", "Test", "test@example.com", Role.DEVELOPER,
                          "provider-session", "test", int(time.time()) + 60)
    assert await logout(current) is None

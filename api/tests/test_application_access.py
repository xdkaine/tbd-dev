"""Application access is mandatory independently of administrator membership."""
import time
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

from app.config import settings
from app.middleware.auth import create_access_token, get_current_user, get_current_user_from_token
from app.services.rbac import Role, resolve_application_role


@pytest.fixture(autouse=True)
def active_provider_for_role_tests(monkeypatch):
    # This file isolates role/profile behavior; session protocol has its own tests.
    from app.services import oidc
    monkeypatch.setattr(oidc, "require_active_session", AsyncMock())



@pytest.mark.parametrize("roles,expected", [
    (["tbd:access", "tbd:user"], Role.DEVELOPER),
    (["tbd:access", "tbd:administrator"], Role.FACULTY),
    (["tbd:access", "tbd:user", "tbd:administrator"], Role.FACULTY),
])
def test_mapped_role(roles, expected):
    assert resolve_application_role({"amr": ["ad"], "application_roles": roles}) == expected


@pytest.mark.parametrize("claims", [
    {"amr": ["ad"], "application_roles": ["tbd:administrator"]},
    {"amr": ["ad"], "application_roles": ["tbd:access"]},
    {"amr": ["ad"], "application_roles": ["cloud:access", "cloud:administrator"]},
    {"amr": ["ad"], "application_roles": ["tbd:access", "cloud:administrator"]},
    {"amr": ["ad"], "groups": ["JAS-Faculty"]},
    {"amr": ["local_break_glass"], "application_roles": ["tbd:access", "tbd:administrator"]},
    {"amr": ["ad", "local_recovery"], "application_roles": ["tbd:access", "tbd:user"]},
    {"amr": "ad", "application_roles": ["tbd:access", "tbd:user"]},
    {"amr": ["ad"], "application_roles": "tbd:access tbd:user"},
])
def test_invalid_access_denied(claims):
    with pytest.raises(HTTPException) as exc:
        resolve_application_role(claims)
    assert exc.value.status_code == 403


async def test_native_login_cannot_bypass(monkeypatch):
    from app.routers.auth import ad_auth_service, login
    from app.schemas.auth import LoginRequest
    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    authenticate = AsyncMock()
    monkeypatch.setattr(ad_auth_service, "authenticate_async", authenticate)
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await login(LoginRequest(username="example", password="example"), db)
    assert exc.value.status_code == 403
    authenticate.assert_not_called()
    db.execute.assert_not_called()


async def test_old_sessions_rejected_for_http_and_sse(monkeypatch):
    token, _ = create_access_token(uuid.uuid4(), "example", Role.FACULTY.value)
    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), db)
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        await get_current_user_from_token(token, db)
    assert exc.value.status_code == 401
    db.execute.assert_not_called()


@pytest.mark.parametrize("remaining", [120, 3600])
def test_mapped_session_expiry_cannot_extend_source(remaining):
    source_expiry = int(time.time()) + remaining
    token, ttl = create_access_token(uuid.uuid4(), "example", Role.DEVELOPER.value,
                                    application_access=True, source_expires_at=source_expiry)
    claims = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    assert claims["access_policy"] == "tbd-application-v1"
    assert claims["exp"] <= source_expiry
    assert ttl <= min(remaining, 600)


async def test_strict_oidc_requires_audience(monkeypatch):
    from app.services.oidc import OidcError, verify_id_token
    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    monkeypatch.setattr(settings, "oidc_issuer", "https://auth.example.com")
    monkeypatch.setattr(settings, "oidc_audience", "")
    with pytest.raises(OidcError):
        await verify_id_token("untrusted")


async def test_oidc_verifier_enforces_audience(monkeypatch):
    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.services import oidc
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    monkeypatch.setattr(settings, "oidc_issuer", "https://auth.example.com")
    monkeypatch.setattr(settings, "oidc_audience", "tbd-client")
    monkeypatch.setattr(oidc, "_get_jwks_uri", AsyncMock(return_value="https://auth.example.com/jwks"))
    public_key = key.public_key()
    class SigningKey:
        key = public_key
    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def get_signing_key_from_jwt(self, token):
            return SigningKey()
    monkeypatch.setattr(pyjwt, "PyJWKClient", Client)
    claims = {"sub": "example", "iss": settings.oidc_issuer,
              "iat": int(time.time()), "exp": int(time.time()) + 120, "aud": "cloud-client"}
    token = pyjwt.encode(claims, key, algorithm="RS256")
    with pytest.raises(oidc.OidcError):
        await oidc.verify_id_token(token)
    claims["aud"] = "tbd-client"
    token = pyjwt.encode(claims, key, algorithm="RS256")
    assert (await oidc.verify_id_token(token))["aud"] == "tbd-client"


async def test_exchange_denies_before_user_upsert(monkeypatch):
    from app.routers.auth import oidc_exchange, oidc_service
    from app.schemas.auth import OidcExchangeRequest
    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    monkeypatch.setattr(oidc_service, "verify_id_token", AsyncMock(return_value={
        "sub": "example", "preferred_username": "example", "amr": ["ad"],
        "application_roles": ["tbd:administrator"], "groups": ["JAS-Faculty"],
    }))
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await oidc_exchange(OidcExchangeRequest(id_token="signed-but-no-access"), db)
    assert exc.value.status_code == 403
    db.execute.assert_not_called()


async def test_minimal_openid_claims_reuse_existing_user(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from app.routers import auth
    from app.schemas.auth import OidcExchangeRequest

    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    monkeypatch.setattr(auth.oidc_service, "verify_id_token", AsyncMock(return_value={
        "sub": "canonical-user", "amr": ["ad"],
        "application_roles": ["tbd:access", "tbd:user"], "exp": int(time.time()) + 120,
    }))
    monkeypatch.setattr(auth, "write_audit_log", AsyncMock())
    user = SimpleNamespace(id=uuid.uuid4(), username="canonical-user",
                           display_name="Known Name", email="known@example.com")
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=user))
    result = await auth.oidc_exchange(OidcExchangeRequest(id_token="signed-openid-minimal"), db)
    decoded = jwt.decode(result.access_token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    assert decoded["username"] == "canonical-user"
    assert decoded["role"] == Role.DEVELOPER.value
    assert user.email == "known@example.com"
    db.execute.assert_awaited_once()


@pytest.mark.parametrize("subject", [None, "", "  ", 42, ["user"]])
async def test_invalid_subject_denied(monkeypatch, subject):
    from app.routers import auth
    from app.schemas.auth import OidcExchangeRequest

    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    monkeypatch.setattr(auth.oidc_service, "verify_id_token", AsyncMock(return_value={
        "sub": subject, "preferred_username": "profile-user", "amr": ["ad"],
        "application_roles": ["tbd:access", "tbd:user"],
    }))
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await auth.oidc_exchange(OidcExchangeRequest(id_token="signed-invalid-subject"), db)
    assert exc.value.status_code == 401
    db.execute.assert_not_called()


@pytest.mark.parametrize("mode", ["valid", "wrong-subject", "failure", "foreign-origin"])
async def test_userinfo_bound_to_subject_and_origin(monkeypatch, mode):
    import httpx

    from app.services import oidc

    monkeypatch.setattr(settings, "oidc_issuer", "https://auth.example.com")
    seen_userinfo = []
    def handler(request):
        if request.url.path.endswith("openid-configuration"):
            origin = "https://untrusted.example" if mode == "foreign-origin" else settings.oidc_issuer
            return httpx.Response(200, json={"userinfo_endpoint": origin + "/me"})
        seen_userinfo.append(request)
        if mode == "failure":
            return httpx.Response(503)
        return httpx.Response(200, json={
            "sub": "other-user" if mode == "wrong-subject" else "canonical-user",
            "preferred_username": "canonical-user", "email": "person@example.com",
            "name": "Person", "application_roles": ["tbd:administrator"], "groups": ["admin"],
        })
    real_client = httpx.AsyncClient
    monkeypatch.setattr(oidc.httpx, "AsyncClient", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(handler)))
    if mode == "valid":
        profile = await oidc.fetch_userinfo("test-access-token", "canonical-user")
        assert profile == {"preferred_username": "canonical-user", "email": "person@example.com",
                           "name": "Person"}
    else:
        with pytest.raises(oidc.OidcError):
            await oidc.fetch_userinfo("test-access-token", "canonical-user")
    if mode == "foreign-origin":
        assert not seen_userinfo


async def test_new_user_without_profile_email_denied(monkeypatch):
    from unittest.mock import Mock

    from app.routers import auth
    from app.schemas.auth import OidcExchangeRequest

    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    monkeypatch.setattr(auth.oidc_service, "verify_id_token", AsyncMock(return_value={
        "sub": "canonical-user", "amr": ["ad"],
        "application_roles": ["tbd:access", "tbd:user"], "exp": int(time.time()) + 120,
    }))
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await auth.oidc_exchange(OidcExchangeRequest(id_token="signed-openid-minimal"), db)
    assert exc.value.status_code == 403
    db.add.assert_not_called()


async def test_exchange_hydrates_profile_but_not_userinfo_roles(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from app.routers import auth
    from app.schemas.auth import OidcExchangeRequest

    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    monkeypatch.setattr(auth.oidc_service, "verify_id_token", AsyncMock(return_value={
        "sub": "canonical-user", "amr": ["ad"],
        "application_roles": ["tbd:access", "tbd:user"], "exp": int(time.time()) + 120,
    }))
    fetch = AsyncMock(return_value={"preferred_username": "canonical-user", "name": "Real Name",
                                   "email": "person@example.com", "application_roles": ["tbd:administrator"]})
    monkeypatch.setattr(auth.oidc_service, "fetch_userinfo", fetch)
    monkeypatch.setattr(auth, "write_audit_log", AsyncMock())
    user = SimpleNamespace(id=uuid.uuid4(), username="canonical-user", display_name="Old", email="old@example.com")
    db = AsyncMock()
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=user))
    result = await auth.oidc_exchange(OidcExchangeRequest(id_token="signed-openid-minimal", access_token="test-access"), db)
    claims = jwt.decode(result.access_token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    assert claims["role"] == Role.DEVELOPER.value
    assert user.email == "person@example.com"
    assert user.display_name == "Real Name"
    fetch.assert_awaited_once_with("test-access", "canonical-user")


async def test_strict_email_collision_cannot_link_or_rename_user(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from app.routers import auth
    from app.schemas.auth import OidcExchangeRequest

    monkeypatch.setattr(settings, "oidc_require_application_access", True)
    monkeypatch.setattr(auth.oidc_service, "verify_id_token", AsyncMock(return_value={
        "sub": "different-subject", "preferred_username": "different-user", "amr": ["ad"],
        "application_roles": ["tbd:access", "tbd:administrator"],
        "email": "shared@example.com", "name": "Different Name", "exp": int(time.time()) + 120,
    }))
    audit = AsyncMock()
    monkeypatch.setattr(auth, "write_audit_log", audit)
    existing = SimpleNamespace(id=uuid.uuid4(), username="existing-user",
                               display_name="Existing Name", email="shared@example.com")
    db = AsyncMock()
    db.execute.side_effect = [Mock(scalar_one_or_none=Mock(return_value=None)),
                              Mock(scalar_one_or_none=Mock(return_value=existing))]
    with pytest.raises(HTTPException) as exc:
        await auth.oidc_exchange(OidcExchangeRequest(id_token="signed-colliding-email"), db)
    assert exc.value.status_code == 403
    assert existing.username == "existing-user"
    assert existing.display_name == "Existing Name"
    db.flush.assert_not_called()
    db.add.assert_not_called()
    audit.assert_not_called()

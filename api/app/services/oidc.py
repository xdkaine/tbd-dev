"""OIDC ID-token verification against the platform auth-service.

The standalone auth-service (oidc-provider) issues RS256 ID tokens carrying
``sub``, ``preferred_username``, ``email``, ``name``, ``groups`` (AD group
CNs) and ``amr`` claims. The web console completes the authorization-code +
PKCE flow and hands us the ID token via ``POST /auth/oidc/exchange``; this
module re-verifies the token against the provider's published JWKS before the
API issues its own short-lived session JWT (same contract as AD login).
"""

import asyncio
import logging
import time

import httpx
import jwt as pyjwt

from app.config import settings

logger = logging.getLogger(__name__)

_DISCOVERY_CACHE_TTL = 300

_discovery_cache: dict = {"fetched_at": 0.0, "jwks_uri": None}


class OidcError(Exception):
    """Raised when an OIDC ID token cannot be verified."""


def _issuer_root() -> str:
    return settings.oidc_issuer.rstrip("/")


async def _get_jwks_uri() -> str:
    """Resolve the JWKS URI from discovery, with a cached standard-path fallback."""
    now = time.monotonic()
    cached = _discovery_cache["jwks_uri"]
    if cached and now - _discovery_cache["fetched_at"] < _DISCOVERY_CACHE_TTL:
        return cached

    jwks_uri: str | None = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_issuer_root()}/.well-known/openid-configuration")
            resp.raise_for_status()
            jwks_uri = resp.json().get("jwks_uri")
    except Exception as exc:  # noqa: BLE001 — fall back to the standard path
        logger.warning("OIDC discovery fetch failed, using fallback JWKS path: %s", exc)

    if not jwks_uri:
        jwks_uri = f"{_issuer_root()}/jwks"

    _discovery_cache["jwks_uri"] = jwks_uri
    _discovery_cache["fetched_at"] = now
    return jwks_uri


async def verify_id_token(id_token: str) -> dict:
    """Verify an OIDC ID token signature/claims and return its payload.

    Checks the RS256 signature against the provider JWKS, then validates
    ``exp``/``sub`` presence, issuer and audience.
    """
    if (not settings.oidc_issuer
            or (settings.oidc_require_application_access and not settings.oidc_audience)):
        raise OidcError("OIDC SSO is not configured")

    try:
        jwks_uri = await _get_jwks_uri()
        client = pyjwt.PyJWKClient(jwks_uri, cache_keys=True)
        signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, id_token)
        claims = pyjwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience or None,
            options={"require": ["exp", "iat", "sub"], "verify_aud": bool(settings.oidc_audience)},
        )
    except pyjwt.PyJWTError as exc:
        raise OidcError(f"ID token verification failed: {exc}") from exc

    iss = str(claims.get("iss", "")).rstrip("/")
    if iss != _issuer_root():
        raise OidcError("ID token issuer mismatch")

    aud = claims.get("aud")
    auds = [aud] if isinstance(aud, str) else list(aud or [])
    if settings.oidc_audience and settings.oidc_audience not in auds:
        raise OidcError("ID token audience mismatch")

    return claims


async def fetch_userinfo(access_token: str, expected_subject: str) -> dict:
    """Fetch optional profile only; authorization remains in the verified ID token."""
    from urllib.parse import urlsplit

    issuer = _issuer_root()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            discovery = await client.get(f"{issuer}/.well-known/openid-configuration")
            discovery.raise_for_status()
            endpoint = discovery.json().get("userinfo_endpoint")
            if not isinstance(endpoint, str):
                raise OidcError("Userinfo endpoint is unavailable")
            parsed = urlsplit(endpoint)
            trusted = urlsplit(issuer)
            if (parsed.scheme != "https" or parsed.username or parsed.password
                    or (parsed.scheme, parsed.hostname, parsed.port)
                    != (trusted.scheme, trusted.hostname, trusted.port)):
                raise OidcError("Userinfo endpoint must use the trusted issuer origin")
            response = await client.get(endpoint, headers={"Authorization": f"Bearer {access_token}"})
            response.raise_for_status()
            profile = response.json()
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise OidcError("Userinfo profile could not be retrieved") from exc
    if not isinstance(profile, dict) or profile.get("sub") != expected_subject:
        raise OidcError("Userinfo subject mismatch")
    return {key: value for key, value in profile.items()
            if key in ("name", "email", "preferred_username") and isinstance(value, str)}


async def session_request(path: str, sid: str, sub: str) -> dict:
    """Query current provider authority without caching successful answers."""
    from urllib.parse import urlsplit
    issuer = _issuer_root()
    parsed = urlsplit(issuer)
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or not settings.oidc_audience or not settings.oidc_client_secret
            or not isinstance(sid, str) or not sid or not isinstance(sub, str) or not sub):
        raise OidcError("Provider session verification is not configured")
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.post(
                f"{issuer}/session/{path}",
                auth=httpx.BasicAuth(settings.oidc_audience, settings.oidc_client_secret),
                data={"sid": sid, "sub": sub},
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid session response")
            return data
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise OidcError("Provider session verification unavailable") from exc


async def require_active_session(sid: str, sub: str) -> None:
    data = await session_request("status", sid, sub)
    if data.get("active") is not True:
        raise OidcError("Provider session has ended")


async def terminate_session(sid: str, sub: str) -> None:
    data = await session_request("backchannel-logout", sid, sub)
    if not isinstance(data.get("destroyed"), bool):
        raise OidcError("Provider did not confirm session termination")

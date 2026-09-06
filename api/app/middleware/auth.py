"""Authentication dependencies for FastAPI routes."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.rbac import Role
from app.services import oidc as oidc_service

security = HTTPBearer()


@dataclass
class CurrentUser:
    """Represents the authenticated user in request context."""

    id: uuid.UUID
    username: str
    display_name: str
    email: str
    role: Role
    provider_sid: str | None = None
    provider_sub: str | None = None
    expires_at: int | None = None


def create_access_token(
    user_id: uuid.UUID, username: str, role: str, *,
    application_access: bool = False, source_expires_at: int | None = None,
    provider_sid: str | None = None, provider_sub: str | None = None,
) -> tuple[str, int]:
    """Create a JWT access token.

    Returns:
        Tuple of (token_string, expires_in_seconds).
    """
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta
    if application_access:
        if not isinstance(source_expires_at, (int, float)) or isinstance(source_expires_at, bool):
            raise HTTPException(status_code=401, detail="SSO token expiry is required")
        expire = min(expire, datetime.fromtimestamp(source_expires_at, timezone.utc),
                     datetime.now(timezone.utc) + timedelta(minutes=10))
    expires_in = max(0, int((expire - datetime.now(timezone.utc)).total_seconds()))

    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    if application_access:
        payload["access_policy"] = "tbd-application-v1"
        payload["provider_sid"] = provider_sid
        payload["provider_sub"] = provider_sub
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


async def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
    *, check_provider: bool = True,
) -> CurrentUser:
    """FastAPI dependency that extracts and validates the current user from JWT.

    Raises HTTPException 401 if the token is invalid or user not found.
    """
    token = credentials.credentials

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        if (settings.oidc_require_application_access
                and payload.get("access_policy") != "tbd-application-v1"):
            raise HTTPException(status_code=401, detail="Sign in again through auth-service SSO")
        user_id_str: str = payload.get("sub")
        username: str = payload.get("username")
        role_str: str = payload.get("role")

        if not user_id_str or not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        user_id = uuid.UUID(user_id_str)

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if check_provider:
        await validate_provider_session(payload)

    # Verify user still exists in DB
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return CurrentUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=Role(role_str),
        provider_sid=payload.get("provider_sid"),
        provider_sub=payload.get("provider_sub"),
        expires_at=payload.get("exp"),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    return await _get_current_user(credentials, db)


async def get_logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    # A previously terminated provider session can still confirm idempotent logout.
    return await _get_current_user(credentials, db, check_provider=False)


def require_role(*allowed_roles: Role):
    """Dependency factory that checks if the current user has one of the allowed roles.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role(Role.STAFF, Role.FACULTY))])
    """

    async def _check_role(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not authorized for this action",
            )
        return current_user

    return _check_role


async def get_current_user_from_token(
    token: str = Query(..., alias="token"),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """FastAPI dependency for SSE endpoints where EventSource cannot set headers.

    Reads the JWT from a `?token=` query parameter instead of the
    Authorization header.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        if (settings.oidc_require_application_access
                and payload.get("access_policy") != "tbd-application-v1"):
            raise HTTPException(status_code=401, detail="Sign in again through auth-service SSO")
        user_id_str: str = payload.get("sub")
        username: str = payload.get("username")
        role_str: str = payload.get("role")

        if not user_id_str or not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        user_id = uuid.UUID(user_id_str)

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    await validate_provider_session(payload)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return CurrentUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=Role(role_str),
        provider_sid=payload.get("provider_sid"),
        provider_sub=payload.get("provider_sub"),
        expires_at=payload.get("exp"),
    )


async def validate_provider_session(payload: dict) -> None:
    if not settings.oidc_require_application_access:
        return
    try:
        await oidc_service.require_active_session(payload.get("provider_sid"), payload.get("provider_sub"))
    except oidc_service.OidcError as exc:
        raise HTTPException(status_code=401, detail="Session ended or could not be verified") from exc


async def require_current_session(current_user: CurrentUser) -> None:
    """Recheck ongoing streams and pending callbacks before releasing data."""
    if current_user.expires_at is not None and datetime.now(timezone.utc).timestamp() >= current_user.expires_at:
        raise HTTPException(status_code=401, detail="Session expired")
    await validate_provider_session({"provider_sid": current_user.provider_sid, "provider_sub": current_user.provider_sub})

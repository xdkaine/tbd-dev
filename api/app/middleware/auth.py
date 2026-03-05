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

security = HTTPBearer()


@dataclass
class CurrentUser:
    """Represents the authenticated user in request context."""

    id: uuid.UUID
    username: str
    display_name: str
    email: str
    role: Role


def create_access_token(user_id: uuid.UUID, username: str, role: str) -> tuple[str, int]:
    """Create a JWT access token.

    Returns:
        Tuple of (token_string, expires_in_seconds).
    """
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta
    expires_in = int(expires_delta.total_seconds())

    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """FastAPI dependency that extracts and validates the current user from JWT.

    Raises HTTPException 401 if the token is invalid or user not found.
    """
    token = credentials.credentials

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
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
    )


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
    )

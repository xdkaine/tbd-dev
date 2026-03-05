"""Auth schemas for login and user info."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """AD login credentials."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """JWT token returned after successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserInfo(BaseModel):
    """Current user information."""

    id: uuid.UUID
    username: str
    display_name: str
    email: str
    role: str
    github_username: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

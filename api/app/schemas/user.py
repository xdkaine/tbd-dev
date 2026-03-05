"""User management schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    """User in admin API responses."""

    id: uuid.UUID
    username: str
    display_name: str
    email: str
    role: str
    github_username: str | None = None
    project_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Paginated list of users."""

    items: list[UserResponse]
    total: int


class UserRoleUpdate(BaseModel):
    """Request to update a user's role mapping."""

    role: str = Field(..., pattern=r"^(JAS_Developer|JAS-Staff|JAS-Faculty)$")

"""Project member schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectMemberAdd(BaseModel):
    """Request to add a user to a project."""

    user_id: uuid.UUID
    role: str = Field(default="contributor", pattern=r"^(contributor)$")


class ProjectMemberResponse(BaseModel):
    """A project member in API responses."""

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    username: str
    display_name: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectMemberListResponse(BaseModel):
    """List of project members."""

    items: list[ProjectMemberResponse]
    total: int


class UserSearchResult(BaseModel):
    """Minimal user info returned from the search endpoint."""

    id: uuid.UUID
    username: str
    display_name: str
    email: str

    model_config = {"from_attributes": True}


class UserSearchResponse(BaseModel):
    """Paginated user search results."""

    items: list[UserSearchResult]
    total: int

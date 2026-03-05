"""Build schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BuildCreate(BaseModel):
    """Request to create a build record."""

    commit_sha: str = Field(..., min_length=7, max_length=64)
    image_ref: str | None = None


class BuildResponse(BaseModel):
    """Build in API responses."""

    id: uuid.UUID
    project_id: uuid.UUID
    commit_sha: str
    image_ref: str | None
    status: str
    trigger: str
    branch: str | None
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class BuildListResponse(BaseModel):
    """List of builds."""

    items: list[BuildResponse]
    total: int


class BuildLogsResponse(BaseModel):
    """Build logs."""

    build_id: uuid.UUID
    status: str
    logs: str | None

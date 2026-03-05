"""Quota schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class QuotaResponse(BaseModel):
    """Quota in API responses."""

    id: uuid.UUID
    project_id: uuid.UUID
    cpu_limit: int
    ram_limit: int  # MB
    disk_limit: int  # MB

    model_config = {"from_attributes": True}


class QuotaUpdate(BaseModel):
    """Request to update project quotas (Faculty only)."""

    cpu_limit: int | None = Field(None, ge=1, le=16, description="vCPU count (1-16)")
    ram_limit: int | None = Field(None, ge=256, le=32768, description="RAM in MB (256-32768)")
    disk_limit: int | None = Field(None, ge=1024, le=102400, description="Disk in MB (1024-102400)")


class QuotaWithProject(BaseModel):
    """Quota with project name for admin listing."""

    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    project_slug: str
    owner_username: str
    cpu_limit: int
    ram_limit: int
    disk_limit: int


class QuotaListResponse(BaseModel):
    """Paginated list of quotas."""

    items: list[QuotaWithProject]
    total: int

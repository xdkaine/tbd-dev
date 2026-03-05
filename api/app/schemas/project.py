"""Project schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RepoResponse(BaseModel):
    """Linked GitHub repository info."""

    id: uuid.UUID
    provider: str
    repo_id: str
    repo_full_name: str | None
    default_branch: str
    install_id: str | None

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    """Request to create a new project."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    repo_url: str | None = None
    default_env: str = Field(default="production", max_length=50)


class ProjectUpdate(BaseModel):
    """Request to update a project."""

    name: str | None = Field(None, min_length=1, max_length=255)
    repo_url: str | None = None
    default_env: str | None = Field(None, max_length=50)
    auto_deploy: bool | None = None
    framework: str | None = Field(None, max_length=50)
    root_directory: str | None = Field(None, max_length=512)
    build_command: str | None = None
    install_command: str | None = None
    output_directory: str | None = Field(None, max_length=512)
    # Health check overrides
    health_check_path: str | None = Field(None, max_length=255)
    health_check_timeout: int | None = Field(None, ge=5, le=600)
    # Deploy notifications
    webhook_url: str | None = Field(None, max_length=1024)
    # Deploy control
    deploy_locked: bool | None = None
    # Project lifecycle
    expires_at: datetime | None = None


class ProjectResponse(BaseModel):
    """Project in API responses."""

    id: uuid.UUID
    name: str
    slug: str
    repo_url: str | None
    owner_id: uuid.UUID
    default_env: str
    auto_deploy: bool
    framework: str | None
    root_directory: str | None = None
    build_command: str | None = None
    install_command: str | None = None
    output_directory: str | None = None
    health_check_path: str | None = None
    health_check_timeout: int | None = None
    webhook_url: str | None = None
    deploy_locked: bool = False
    expires_at: datetime | None = None
    production_url: str | None = None
    repo: RepoResponse | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""

    items: list[ProjectResponse]
    total: int

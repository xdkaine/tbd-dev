"""Template schemas — request/response models for the template catalog and deploy."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TemplateResponse(BaseModel):
    """Template in API responses."""

    id: uuid.UUID
    name: str
    slug: str
    description: str
    framework: str
    github_owner: str
    github_repo: str
    icon_url: str | None = None
    tags: list[str] = []
    sort_order: int = 0
    active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    """List of templates."""

    items: list[TemplateResponse]
    total: int


class TemplateCreate(BaseModel):
    """Admin request to add a template to the catalog."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str = Field(default="", max_length=2000)
    framework: str = Field(..., max_length=50)
    github_owner: str = Field(default="xdkaine/tbd-dev", max_length=255)
    github_repo: str = Field(..., max_length=255)
    icon_url: str | None = Field(None, max_length=1024)
    tags: list[str] = Field(default_factory=list)
    sort_order: int = Field(default=0, ge=0)


class TemplateUpdate(BaseModel):
    """Admin request to update a template."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    framework: str | None = Field(None, max_length=50)
    github_owner: str | None = Field(None, max_length=255)
    github_repo: str | None = Field(None, max_length=255)
    icon_url: str | None = Field(None, max_length=1024)
    tags: list[str] | None = None
    sort_order: int | None = Field(None, ge=0)
    active: bool | None = None


class TemplateDeployRequest(BaseModel):
    """User request to deploy a template — creates a new repo + project."""

    repo_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9._-]+$",
        description="Name for the new GitHub repository",
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Repository description",
    )
    private: bool = Field(
        default=False,
        description="Whether the new repo should be private",
    )


class TemplateDeployResponse(BaseModel):
    """Response after deploying a template."""

    project_id: uuid.UUID
    project_slug: str
    repo_full_name: str
    repo_html_url: str
    build_id: uuid.UUID | None = None
    message: str

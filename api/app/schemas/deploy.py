"""Deploy schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DeployCreate(BaseModel):
    """Request to create a deployment."""

    env: str = Field(..., description="Environment name (e.g. 'production', 'preview')")
    image_ref: str = Field(..., description="OCI image reference in the registry")
    project: str | None = Field(None, description="Project slug (used by GitHub Actions)")


class DeployResponse(BaseModel):
    """Deploy in API responses."""

    id: uuid.UUID
    env_id: uuid.UUID
    artifact_id: uuid.UUID | None
    status: str
    url: str | None
    created_at: datetime
    promoted_at: datetime | None

    model_config = {"from_attributes": True}


class DeployListResponse(BaseModel):
    """List of deploys."""

    items: list[DeployResponse]
    total: int


class RollbackRequest(BaseModel):
    """Request to rollback a deployment."""

    reason: str | None = Field(None, max_length=1024)


class DeployLogsResponse(BaseModel):
    """Deploy logs."""

    deploy_id: uuid.UUID
    status: str
    logs: str | None

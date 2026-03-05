"""Secret schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SecretCreate(BaseModel):
    """Request to create a secret."""

    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Z_][A-Z0-9_]*$")
    value: str = Field(..., min_length=1)
    scope: str = Field(
        default="project",
        pattern=r"^(project|production|staging|preview)$",
    )


class SecretResponse(BaseModel):
    """Secret in API responses (value is never exposed)."""

    id: uuid.UUID
    project_id: uuid.UUID
    scope: str
    key: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SecretListResponse(BaseModel):
    """List of secrets."""

    items: list[SecretResponse]
    total: int

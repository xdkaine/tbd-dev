"""Environment schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EnvironmentCreate(BaseModel):
    """Request to create a new environment."""

    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(
        ..., pattern=r"^(production|staging|preview)$", description="Environment type"
    )


class EnvironmentResponse(BaseModel):
    """Environment in API responses."""

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    type: str
    vlan_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EnvironmentListResponse(BaseModel):
    """List of environments."""

    items: list[EnvironmentResponse]
    total: int

"""Network schemas."""

import uuid

from pydantic import BaseModel


class VlanResponse(BaseModel):
    """VLAN allocation in API responses."""

    id: uuid.UUID
    vlan_tag: int
    subnet_cidr: str
    reserved_by_project_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class VlanListResponse(BaseModel):
    """List of VLANs."""

    items: list[VlanResponse]
    total: int


class VlanReserveRequest(BaseModel):
    """Request to reserve a VLAN for a project."""

    project_id: uuid.UUID

"""Network policy schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NetworkPolicyResponse(BaseModel):
    """Network policy in API responses."""

    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str | None = None
    name: str
    direction: str  # 'egress' or 'ingress'
    protocol: str  # 'tcp', 'udp', 'icmp', 'any'
    port: int | None
    destination: str  # CIDR or hostname
    action: str  # 'allow' or 'deny'
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NetworkPolicyCreate(BaseModel):
    """Request to create a network policy."""

    project_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    direction: str = Field(default="egress", pattern=r"^(egress|ingress)$")
    protocol: str = Field(default="tcp", pattern=r"^(tcp|udp|icmp|any)$")
    port: int | None = Field(None, ge=1, le=65535)
    destination: str = Field(..., min_length=1, max_length=255)
    action: str = Field(default="allow", pattern=r"^(allow|deny)$")


class NetworkPolicyUpdate(BaseModel):
    """Request to update a network policy."""

    name: str | None = Field(None, min_length=1, max_length=255)
    protocol: str | None = Field(None, pattern=r"^(tcp|udp|icmp|any)$")
    port: int | None = Field(None, ge=1, le=65535)
    destination: str | None = Field(None, min_length=1, max_length=255)
    action: str | None = Field(None, pattern=r"^(allow|deny)$")
    enabled: bool | None = None


class NetworkPolicyListResponse(BaseModel):
    """Paginated list of network policies."""

    items: list[NetworkPolicyResponse]
    total: int

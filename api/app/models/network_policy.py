"""Network policy model - egress/ingress firewall rules per project."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class NetworkPolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Firewall rule for a project's network traffic.

    Default posture is deny-all egress. Staff/Faculty create
    explicit allow rules for legitimate traffic (e.g. DNS, HTTPS,
    package registries).
    """

    __tablename__ = "network_policies"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False, default="egress"
    )  # 'egress' or 'ingress'
    protocol: Mapped[str] = mapped_column(
        String(10), nullable=False, default="tcp"
    )  # 'tcp', 'udp', 'icmp', 'any'
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    destination: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # CIDR or hostname
    action: Mapped[str] = mapped_column(
        String(10), nullable=False, default="allow"
    )  # 'allow' or 'deny'
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="network_policies")  # noqa: F821

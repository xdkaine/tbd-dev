"""Environment model."""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Environment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A deployment environment within a project (production, staging, preview)."""

    __tablename__ = "environments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'production', 'staging', 'preview'
    vlan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vlans.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="environments")  # noqa: F821
    deploys: Mapped[list["Deploy"]] = relationship(  # noqa: F821
        back_populates="environment", lazy="selectin", cascade="all, delete-orphan"
    )

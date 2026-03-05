"""Audit log model."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable audit log entry for all platform mutations."""

    __tablename__ = "audit_log"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. 'project.create'
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. 'project'
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)  # UUID as string
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON payload

    # Relationships
    actor: Mapped["User | None"] = relationship(back_populates="audit_entries")  # noqa: F821

"""Secret model with encrypted values."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Secret(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An encrypted secret scoped to a project and environment."""

    __tablename__ = "secrets"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(50), nullable=False, default="project"
    )  # 'project', 'production', 'staging', 'preview'
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="secrets")  # noqa: F821

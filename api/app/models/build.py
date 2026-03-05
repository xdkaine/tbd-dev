"""Build and Artifact models."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Build(Base, UUIDPrimaryKeyMixin):
    """A build triggered by a commit push or PR event."""

    __tablename__ = "builds"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    image_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="queued"
    )  # queued, building, success, failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # manual, push, pull_request
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="builds")  # noqa: F821
    artifact: Mapped["Artifact | None"] = relationship(
        back_populates="build", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )


class Artifact(Base, UUIDPrimaryKeyMixin):
    """An OCI image artifact produced by a build."""

    __tablename__ = "artifacts"

    build_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("builds.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    image_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    stored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    build: Mapped["Build"] = relationship(back_populates="artifact")
    deploys: Mapped[list["Deploy"]] = relationship(  # noqa: F821
        back_populates="artifact", lazy="selectin"
    )

"""Project, Repo, and ProjectMember models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A deployable project owned by a user."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    repo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    default_env: Mapped[str] = mapped_column(String(50), nullable=False, default="production")
    auto_deploy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    framework: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Build settings (Vercel-style overrides)
    root_directory: Mapped[str | None] = mapped_column(String(512), nullable=True)
    build_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    install_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_directory: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Health check configuration (per-project overrides)
    health_check_path: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None,
        comment="Custom health check path (default: /)",
    )
    health_check_timeout: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None,
        comment="Health check total timeout in seconds (default: 60)",
    )

    # Deploy notifications
    webhook_url: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, default=None,
        comment="Webhook URL for deploy notifications (POST on success/failure)",
    )

    # Deploy control
    deploy_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="When true, new deploys are blocked (deploy freeze)",
    )

    # Project lifecycle
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
        comment="Auto-archive/disable date (semester end)",
    )

    # Persistent production URL (Vercel-style vanity URL)
    production_url: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, default=None,
        comment="Persistent production URL: <slug>-<username>.dev.sdc.cpp",
    )

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    repo: Mapped["Repo | None"] = relationship(
        back_populates="project", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    environments: Mapped[list["Environment"]] = relationship(  # noqa: F821
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    builds: Mapped[list["Build"]] = relationship(  # noqa: F821
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    secrets: Mapped[list["Secret"]] = relationship(  # noqa: F821
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    vlan: Mapped["Vlan | None"] = relationship(  # noqa: F821
        back_populates="project", uselist=False, lazy="selectin"
    )
    quota: Mapped["Quota | None"] = relationship(  # noqa: F821
        back_populates="project", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    network_policies: Mapped[list["NetworkPolicy"]] = relationship(  # noqa: F821
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )


class Repo(Base, UUIDPrimaryKeyMixin):
    """GitHub repository linked to a project."""

    __tablename__ = "repos"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="github")
    repo_id: Mapped[str] = mapped_column(String(255), nullable=False)  # GitHub repo numeric ID
    repo_full_name: Mapped[str | None] = mapped_column(String(512), nullable=True)  # owner/repo
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    install_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # GitHub App install ID
    created_from_template: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if this repo was created via a TBD template",
    )
    template_slug: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Template slug used to create this repo (if any)",
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="repo")


class ProjectMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user who has been added as a contributor to a project.

    The unique constraint on (project_id, user_id) handles race conditions
    where multiple people might try to add the same user concurrently.
    """

    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="contributor"
    )  # 'contributor' — extensible for future roles like 'viewer'

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="project_memberships")  # noqa: F821

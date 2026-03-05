"""User, Group, and GroupRoleMap models."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Platform user, synced from Active Directory."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ad_dn: Mapped[str] = mapped_column(String(1024), nullable=False)

    # GitHub account linking (OAuth)
    github_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    projects: Mapped[list["Project"]] = relationship(  # noqa: F821
        back_populates="owner", lazy="selectin"
    )
    project_memberships: Mapped[list["ProjectMember"]] = relationship(  # noqa: F821
        back_populates="user", lazy="selectin"
    )
    audit_entries: Mapped[list["AuditLog"]] = relationship(  # noqa: F821
        back_populates="actor", lazy="selectin"
    )


class Group(Base, UUIDPrimaryKeyMixin):
    """Active Directory group mapped to platform roles."""

    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ad_dn: Mapped[str] = mapped_column(String(1024), nullable=False)

    # Relationships
    role_mappings: Mapped[list["GroupRoleMap"]] = relationship(
        back_populates="group", lazy="selectin", cascade="all, delete-orphan"
    )


class GroupRoleMap(Base, UUIDPrimaryKeyMixin):
    """Maps an AD group to a platform role (JAS_Developer, JAS-Staff, JAS-Faculty)."""

    __tablename__ = "group_role_map"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'JAS_Developer', 'JAS-Staff', 'JAS-Faculty'

    # Relationships
    group: Mapped["Group"] = relationship(back_populates="role_mappings")

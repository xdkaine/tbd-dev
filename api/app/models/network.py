"""Network models: VLAN allocation and project quotas."""

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class Vlan(Base, UUIDPrimaryKeyMixin):
    """VLAN allocation for project network segmentation.

    Formula: VLAN tag = 1000 + N, subnet = 172.16.N.0/25
    """

    __tablename__ = "vlans"

    vlan_tag: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    subnet_cidr: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    reserved_by_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )

    # Relationships
    project: Mapped["Project | None"] = relationship(back_populates="vlan")  # noqa: F821


class Quota(Base, UUIDPrimaryKeyMixin):
    """Resource quotas for a project."""

    __tablename__ = "quotas"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    cpu_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=2)  # vCPUs
    ram_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)  # MB
    disk_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10240)  # MB

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="quota")  # noqa: F821

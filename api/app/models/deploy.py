"""Deploy model with state machine states."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


# Deploy state machine states
DEPLOY_STATES = [
    "queued",
    "building",
    "artifact_ready",
    "provisioning",
    "healthy",
    "active",
    "stopped",     # container intentionally stopped (can be restarted)
    "failed",
    "rolled_back",
    "superseded",
]

# Valid state transitions
DEPLOY_TRANSITIONS = {
    "queued": ["building", "failed"],
    "building": ["artifact_ready", "failed"],
    "artifact_ready": ["provisioning", "failed"],
    "provisioning": ["healthy", "failed"],
    "healthy": ["active", "failed"],
    "active": ["superseded", "rolled_back", "stopped"],
    "stopped": ["active", "rolled_back"],  # restart or rollback
    "failed": ["queued", "rolled_back"],  # retry or rollback
    "rolled_back": [],  # terminal
    "superseded": [],  # terminal
}


class Deploy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A deployment of an artifact to an environment."""

    __tablename__ = "deploys"

    env_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=False
    )
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Container tracking — persisted so IP allocation, teardown, and the
    # reconciler have an authoritative source of truth (not just Proxmox runtime).
    container_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    container_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    container_vmid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    container_node: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    environment: Mapped["Environment"] = relationship(back_populates="deploys")  # noqa: F821
    artifact: Mapped["Artifact | None"] = relationship(back_populates="deploys")  # noqa: F821

    def can_transition_to(self, new_status: str) -> bool:
        """Check if a state transition is valid."""
        return new_status in DEPLOY_TRANSITIONS.get(self.status, [])

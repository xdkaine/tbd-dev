"""Add network_policies table for per-project firewall rules.

Stores egress/ingress allow/deny rules that map to iptables or
nftables entries on the Proxmox host for each project's LXC container.

Revision ID: 007
Revises: 006
Create Date: 2026-03-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    """Check if a table already exists in the database."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_schema = 'public' AND table_name = :name"
            ")"
        ),
        {"name": table_name},
    )
    return result.scalar()


def upgrade() -> None:
    if _table_exists("network_policies"):
        return

    op.create_table(
        "network_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False, server_default="egress"),
        sa.Column("protocol", sa.String(10), nullable=False, server_default="tcp"),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("action", sa.String(10), nullable=False, server_default="allow"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("network_policies")

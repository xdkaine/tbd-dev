"""Add container tracking columns to deploys table.

Stores container_ip, container_port, container_vmid, and container_node
so the system has an authoritative source of truth for IP allocation,
teardown, and reconciliation (instead of relying solely on Proxmox
runtime scanning).

Includes a partial unique index on container_ip for non-terminal deploys
to prevent duplicate IP assignments at the database level.

Revision ID: 012
Revises: 011
Create Date: 2026-03-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column already exists in a table."""
    from sqlalchemy import inspect as sa_inspect
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def _index_exists(index_name: str) -> bool:
    """Check if an index already exists."""
    from sqlalchemy import inspect as sa_inspect
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    indexes = inspector.get_indexes("deploys")
    return any(idx["name"] == index_name for idx in indexes)


def upgrade() -> None:
    # Container IP (bare IP without CIDR, e.g. "10.128.30.80")
    if not _column_exists("deploys", "container_ip"):
        op.add_column(
            "deploys",
            sa.Column("container_ip", sa.String(45), nullable=True),
        )

    # Container port (e.g. 3000)
    if not _column_exists("deploys", "container_port"):
        op.add_column(
            "deploys",
            sa.Column("container_port", sa.Integer(), nullable=True),
        )

    # Proxmox VMID (e.g. 100)
    if not _column_exists("deploys", "container_vmid"):
        op.add_column(
            "deploys",
            sa.Column("container_vmid", sa.Integer(), nullable=True),
        )

    # Proxmox node name (e.g. "pve1")
    if not _column_exists("deploys", "container_node"):
        op.add_column(
            "deploys",
            sa.Column("container_node", sa.String(100), nullable=True),
        )

    # Partial unique index: no two non-terminal deploys may share the same IP.
    # This is the DB-level safety net for the IP allocation TOCTOU fix.
    if not _index_exists("ix_deploys_active_container_ip"):
        op.create_index(
            "ix_deploys_active_container_ip",
            "deploys",
            ["container_ip"],
            unique=True,
            postgresql_where=sa.text(
                "container_ip IS NOT NULL "
                "AND status NOT IN ('superseded', 'rolled_back', 'failed')"
            ),
        )


def downgrade() -> None:
    if _index_exists("ix_deploys_active_container_ip"):
        op.drop_index("ix_deploys_active_container_ip", table_name="deploys")

    for col in ("container_node", "container_vmid", "container_port", "container_ip"):
        if _column_exists("deploys", col):
            op.drop_column("deploys", col)

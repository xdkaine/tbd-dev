"""Add production_url column to projects table.

Stores the persistent production URL (<slug>-<username>.dev.sdc.cpp)
that auto-switches when a new deploy is promoted.

Revision ID: 011
Revises: 010
Create Date: 2026-03-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column already exists in a table."""
    from sqlalchemy import inspect as sa_inspect
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not _column_exists("projects", "production_url"):
        op.add_column(
            "projects",
            sa.Column(
                "production_url",
                sa.String(1024),
                nullable=True,
                comment="Persistent production URL: <slug>-<username>.dev.sdc.cpp",
            ),
        )


def downgrade() -> None:
    if _column_exists("projects", "production_url"):
        op.drop_column("projects", "production_url")

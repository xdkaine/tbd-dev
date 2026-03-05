"""Add build settings columns to projects table.

Stores per-project overrides for root_directory, build_command,
install_command, and output_directory (Vercel-style build settings).

Revision ID: 006
Revises: 005
Create Date: 2026-03-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("root_directory", sa.String(512), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("build_command", sa.Text(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("install_command", sa.Text(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("output_directory", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "output_directory")
    op.drop_column("projects", "install_command")
    op.drop_column("projects", "build_command")
    op.drop_column("projects", "root_directory")

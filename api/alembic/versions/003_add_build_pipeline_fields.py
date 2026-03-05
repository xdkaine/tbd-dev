"""Add build pipeline fields: auto_deploy/framework on projects, trigger/branch/logs on builds.

Revision ID: 003
Revises: 002
Create Date: 2026-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- projects --
    op.add_column(
        "projects",
        sa.Column("auto_deploy", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "projects",
        sa.Column("framework", sa.String(50), nullable=True),
    )

    # -- builds --
    op.add_column(
        "builds",
        sa.Column("trigger", sa.String(20), nullable=False, server_default="manual"),
    )
    op.add_column(
        "builds",
        sa.Column("branch", sa.String(255), nullable=True),
    )
    op.add_column(
        "builds",
        sa.Column("logs", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("builds", "logs")
    op.drop_column("builds", "branch")
    op.drop_column("builds", "trigger")
    op.drop_column("projects", "framework")
    op.drop_column("projects", "auto_deploy")

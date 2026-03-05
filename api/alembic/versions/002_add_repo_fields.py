"""Add repo_full_name and default_branch to repos table.

Revision ID: 002
Revises: 001
Create Date: 2026-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repos",
        sa.Column("repo_full_name", sa.String(512), nullable=True),
    )
    op.add_column(
        "repos",
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
    )


def downgrade() -> None:
    op.drop_column("repos", "default_branch")
    op.drop_column("repos", "repo_full_name")

"""Add github_token column to users table for storing OAuth access tokens.

Revision ID: 005
Revises: 004
Create Date: 2026-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("github_token", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "github_token")

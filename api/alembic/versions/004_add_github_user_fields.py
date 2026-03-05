"""Add github_id and github_username columns to users table for OAuth account linking.

Revision ID: 004
Revises: 003
Create Date: 2026-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("github_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("github_username", sa.String(255), nullable=True),
    )
    op.create_unique_constraint("uq_users_github_id", "users", ["github_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_github_id", "users", type_="unique")
    op.drop_column("users", "github_username")
    op.drop_column("users", "github_id")

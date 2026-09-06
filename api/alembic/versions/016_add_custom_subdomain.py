"""Add configurable globally unique production subdomains.

Revision ID: 016
Revises: 015
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "custom_subdomain",
            sa.String(length=63),
            nullable=True,
            comment="Globally unique DNS label for the production URL",
        ),
    )
    op.execute("UPDATE projects SET custom_subdomain = slug")
    op.alter_column("projects", "custom_subdomain", nullable=False)
    op.create_index(
        "ix_projects_custom_subdomain",
        "projects",
        ["custom_subdomain"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_projects_custom_subdomain", table_name="projects")
    op.drop_column("projects", "custom_subdomain")

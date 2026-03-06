"""Add template tracking columns to repos table.

Adds created_from_template and template_slug columns to the repos table
so we can track which repositories were created via the template deploy flow.

Revision ID: 014
Revises: 013
Create Date: 2026-03-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repos",
        sa.Column(
            "created_from_template",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True if this repo was created via a TBD template",
        ),
    )
    op.add_column(
        "repos",
        sa.Column(
            "template_slug",
            sa.String(255),
            nullable=True,
            comment="Template slug used to create this repo (if any)",
        ),
    )


def downgrade() -> None:
    op.drop_column("repos", "template_slug")
    op.drop_column("repos", "created_from_template")

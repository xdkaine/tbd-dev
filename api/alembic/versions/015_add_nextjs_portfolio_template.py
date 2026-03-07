"""Add Next.js Portfolio template to the templates catalog.

Seeds the nextjs-portfolio starter template for college-level
web development curriculum (portfolio/CV site).

Revision ID: 015
Revises: 014
Create Date: 2026-03-07
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SLUG = "nextjs-portfolio"


def upgrade() -> None:
    templates_table = sa.table(
        "templates",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("description", sa.Text),
        sa.column("framework", sa.String),
        sa.column("github_owner", sa.String),
        sa.column("github_repo", sa.String),
        sa.column("icon_url", sa.String),
        sa.column("tags", JSON),
        sa.column("sort_order", sa.Integer),
        sa.column("active", sa.Boolean),
    )

    op.bulk_insert(
        templates_table,
        [
            {
                "id": uuid.uuid4(),
                "name": "Next.js Portfolio",
                "slug": SLUG,
                "description": (
                    "A developer portfolio / CV site built with Next.js 14, "
                    "Tailwind CSS, and TypeScript. Includes hero, about, skills, "
                    "projects, experience, education, and contact sections with "
                    "easy-to-edit data blocks at the top of the page."
                ),
                "framework": "nextjs",
                "github_owner": "xdkaine/tbd-dev",
                "github_repo": "nextjs-portfolio",
                "icon_url": None,
                "tags": [
                    "portfolio",
                    "cv",
                    "tailwind",
                    "typescript",
                    "starter",
                    "education",
                ],
                "sort_order": 1,  # right after the landing page
                "active": True,
            },
        ],
    )


def downgrade() -> None:
    # Remove the seeded template row
    op.execute(
        sa.text("DELETE FROM templates WHERE slug = :slug"),
        {"slug": SLUG},
    )

"""Add templates table and seed initial starter templates.

Creates the templates catalog table for curated starter projects.
Seeds the table with one template per supported framework.

NOTE: Template files are stored in the main TBD repo under templates/<slug>/
and are pushed to new user repos via GitHub's Git Data API at deploy time.
The github_owner column is kept for legacy/override purposes but is not used
by the deploy flow — the source repo is configured via TEMPLATE_SOURCE_REPO.

Starter templates are adapted from Vercel's open-source examples
(https://github.com/vercel/vercel/tree/main/examples) under the Apache 2.0
license, with TBD-specific additions (Dockerfile, /health endpoint, $PORT
binding) for container-based deployment on Proxmox/LXC.

Revision ID: 013
Revises: 012
Create Date: 2026-03-05
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    """Check if a table already exists."""
    from sqlalchemy import inspect as sa_inspect
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("templates"):
        op.create_table(
            "templates",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("slug", sa.String(255), nullable=False, unique=True, index=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("framework", sa.String(50), nullable=False),
            sa.Column(
                "github_owner", sa.String(255), nullable=False,
                server_default="xdkaine/tbd-dev",
            ),
            sa.Column("github_repo", sa.String(255), nullable=False),
            sa.Column("icon_url", sa.String(1024), nullable=True),
            sa.Column("tags", JSON, nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # Seed initial templates
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

    seeds = [
        {
            "id": uuid.uuid4(),
            "name": "Next.js Landing Page",
            "slug": "nextjs-landing-page",
            "description": (
                "A modern landing page built with Next.js 14, Tailwind CSS, "
                "and TypeScript. Includes responsive layout, hero section, "
                "features grid, and footer."
            ),
            "framework": "nextjs",
            "github_owner": "xdkaine/tbd-dev",
            "github_repo": "nextjs-landing-page",
            "icon_url": None,
            "tags": ["landing-page", "tailwind", "typescript", "starter"],
            "sort_order": 0,
            "active": True,
        },
        {
            "id": uuid.uuid4(),
            "name": "React + Vite Starter",
            "slug": "react-vite-starter",
            "description": (
                "A clean React single-page application powered by Vite "
                "with Tailwind CSS, React Router, and TypeScript."
            ),
            "framework": "react-vite",
            "github_owner": "xdkaine/tbd-dev",
            "github_repo": "react-vite-starter",
            "icon_url": None,
            "tags": ["spa", "vite", "tailwind", "typescript"],
            "sort_order": 1,
            "active": True,
        },
        {
            "id": uuid.uuid4(),
            "name": "Python FastAPI",
            "slug": "python-fastapi",
            "description": (
                "A Python web API built with FastAPI. Includes health endpoint, "
                "structured logging, and a Dockerfile ready to deploy."
            ),
            "framework": "python",
            "github_owner": "xdkaine/tbd-dev",
            "github_repo": "python-fastapi",
            "icon_url": None,
            "tags": ["api", "fastapi", "python"],
            "sort_order": 2,
            "active": True,
        },
        {
            "id": uuid.uuid4(),
            "name": "Node.js Express",
            "slug": "nodejs-express",
            "description": (
                "A Node.js web server built with Express. Includes health "
                "endpoint, structured logging, and production-ready Dockerfile."
            ),
            "framework": "nodejs",
            "github_owner": "xdkaine/tbd-dev",
            "github_repo": "nodejs-express",
            "icon_url": None,
            "tags": ["api", "express", "nodejs"],
            "sort_order": 3,
            "active": True,
        },
        {
            "id": uuid.uuid4(),
            "name": "Go Web Server",
            "slug": "go-web",
            "description": (
                "A lightweight Go web server using the standard library. "
                "Includes health endpoint, graceful shutdown, and multi-stage "
                "Dockerfile for a minimal image."
            ),
            "framework": "go",
            "github_owner": "xdkaine/tbd-dev",
            "github_repo": "go-web",
            "icon_url": None,
            "tags": ["api", "go", "minimal"],
            "sort_order": 4,
            "active": True,
        },
        {
            "id": uuid.uuid4(),
            "name": "Static Site",
            "slug": "static-site",
            "description": (
                "A simple static website with HTML, CSS, and vanilla JavaScript. "
                "Served by Nginx with a lightweight Dockerfile."
            ),
            "framework": "static",
            "github_owner": "xdkaine/tbd-dev",
            "github_repo": "static-site",
            "icon_url": None,
            "tags": ["html", "css", "static", "beginner"],
            "sort_order": 5,
            "active": True,
        },
    ]

    op.bulk_insert(templates_table, seeds)


def downgrade() -> None:
    if _table_exists("templates"):
        op.drop_table("templates")

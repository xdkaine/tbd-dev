"""Add project health check, webhook, deploy lock, and lifecycle fields.

Revision ID: 010
Revises: 009
Create Date: 2026-03-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column already exists in a table."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.columns"
            "  WHERE table_schema = 'public'"
            "    AND table_name = :table AND column_name = :col"
            ")"
        ),
        {"table": table_name, "col": column_name},
    )
    return result.scalar()


def upgrade() -> None:
    # Health check configuration (per-project overrides)
    if not _column_exists("projects", "health_check_path"):
        op.add_column(
            "projects",
            sa.Column(
                "health_check_path",
                sa.String(255),
                nullable=True,
                comment="Custom health check path (default: /)",
            ),
        )
    if not _column_exists("projects", "health_check_timeout"):
        op.add_column(
            "projects",
            sa.Column(
                "health_check_timeout",
                sa.Integer(),
                nullable=True,
                comment="Health check total timeout in seconds (default: 60)",
            ),
        )

    # Deploy notifications
    if not _column_exists("projects", "webhook_url"):
        op.add_column(
            "projects",
            sa.Column(
                "webhook_url",
                sa.String(1024),
                nullable=True,
                comment="Webhook URL for deploy notifications (POST on success/failure)",
            ),
        )

    # Deploy freeze / lock
    if not _column_exists("projects", "deploy_locked"):
        op.add_column(
            "projects",
            sa.Column(
                "deploy_locked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
                comment="When true, new deploys are blocked (deploy freeze)",
            ),
        )

    # Project lifecycle — auto-expiry
    if not _column_exists("projects", "expires_at"):
        op.add_column(
            "projects",
            sa.Column(
                "expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="Auto-archive/disable date (semester end)",
            ),
        )


def downgrade() -> None:
    op.drop_column("projects", "expires_at")
    op.drop_column("projects", "deploy_locked")
    op.drop_column("projects", "webhook_url")
    op.drop_column("projects", "health_check_timeout")
    op.drop_column("projects", "health_check_path")

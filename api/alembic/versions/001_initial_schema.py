"""Initial schema - all 13 tables.

Revision ID: 001
Revises: 
Create Date: 2026-03-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("ad_dn", sa.String(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- groups ---
    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("ad_dn", sa.String(1024), nullable=False),
    )

    # --- group_role_map ---
    op.create_table(
        "group_role_map",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(50), nullable=False),
    )

    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("repo_url", sa.String(1024), nullable=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("default_env", sa.String(50), nullable=False, server_default="production"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- repos ---
    op.create_table(
        "repos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False, server_default="github"),
        sa.Column("repo_id", sa.String(255), nullable=False),
        sa.Column("install_id", sa.String(255), nullable=True),
    )

    # --- vlans ---
    op.create_table(
        "vlans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vlan_tag", sa.Integer, unique=True, nullable=False),
        sa.Column("subnet_cidr", sa.String(50), unique=True, nullable=False),
        sa.Column(
            "reserved_by_project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            unique=True,
            nullable=True,
        ),
    )

    # --- environments ---
    op.create_table(
        "environments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column(
            "vlan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vlans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- builds ---
    op.create_table(
        "builds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commit_sha", sa.String(64), nullable=False),
        sa.Column("image_ref", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- artifacts ---
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "build_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("builds.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("image_ref", sa.String(1024), nullable=False),
        sa.Column("sha256", sa.String(128), nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- deploys ---
    op.create_table(
        "deploys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "env_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- secrets ---
    op.create_table(
        "secrets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(50), nullable=False, server_default="project"),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value_encrypted", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- quotas ---
    op.create_table(
        "quotas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("cpu_limit", sa.Integer, nullable=False, server_default="2"),
        sa.Column("ram_limit", sa.Integer, nullable=False, server_default="2048"),
        sa.Column("disk_limit", sa.Integer, nullable=False, server_default="10240"),
    )

    # --- audit_log ---
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("payload", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- Indexes for performance ---
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_target", "audit_log", ["target_type", "target_id"])
    op.create_index("ix_audit_log_actor", "audit_log", ["actor_user_id"])
    op.create_index("ix_audit_log_created", "audit_log", ["created_at"])
    op.create_index("ix_builds_project", "builds", ["project_id"])
    op.create_index("ix_deploys_env", "deploys", ["env_id"])
    op.create_index("ix_environments_project", "environments", ["project_id"])
    op.create_index("ix_secrets_project_key", "secrets", ["project_id", "key"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("quotas")
    op.drop_table("secrets")
    op.drop_table("deploys")
    op.drop_table("artifacts")
    op.drop_table("builds")
    op.drop_table("environments")
    op.drop_table("vlans")
    op.drop_table("repos")
    op.drop_table("projects")
    op.drop_table("group_role_map")
    op.drop_table("groups")
    op.drop_table("users")

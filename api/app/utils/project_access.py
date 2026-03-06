"""Shared project access helpers for contributor checks.

Used across multiple routers to verify that a user (especially a Developer)
can access a project they don't own but are a contributor on.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectMember


async def is_project_contributor(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Check if a user is a contributor (member) on a project."""
    result = await db.execute(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None

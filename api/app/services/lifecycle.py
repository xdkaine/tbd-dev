"""Project lifecycle service — enforces expires_at and other time-based policies.

Runs as a background task during application lifespan, checking periodically
for projects that have passed their expiry date and auto-locking them.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.project import Project
from app.services.audit import write_audit_log

logger = logging.getLogger(__name__)

# How often to check for expired projects (seconds)
_CHECK_INTERVAL = 300  # 5 minutes


async def _enforce_expiry_cycle() -> int:
    """Run one enforcement cycle. Returns the number of projects locked."""
    locked_count = 0
    now = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        # Find projects that are past their expiry date but not yet locked
        result = await db.execute(
            select(Project).where(
                and_(
                    Project.expires_at.isnot(None),
                    Project.expires_at <= now,
                    Project.deploy_locked == False,  # noqa: E712
                )
            )
        )
        expired_projects = result.scalars().all()

        for project in expired_projects:
            project.deploy_locked = True
            logger.info(
                "Auto-locked expired project '%s' (id=%s, expired_at=%s)",
                project.slug,
                project.id,
                project.expires_at,
            )

            await write_audit_log(
                db,
                actor_user_id=None,  # system action
                action="project.auto_locked",
                target_type="project",
                target_id=str(project.id),
                payload={
                    "reason": "expires_at_reached",
                    "expires_at": project.expires_at.isoformat() if project.expires_at else None,
                },
            )
            locked_count += 1

        if locked_count > 0:
            await db.commit()
            logger.info("Lifecycle enforcement: locked %d expired projects", locked_count)

    return locked_count


async def run_lifecycle_loop() -> None:
    """Background loop that periodically enforces project lifecycle rules.

    Designed to be launched as an asyncio task during app lifespan.
    Runs indefinitely until cancelled.
    """
    logger.info("Project lifecycle service started (interval=%ds)", _CHECK_INTERVAL)

    while True:
        try:
            await _enforce_expiry_cycle()
        except asyncio.CancelledError:
            logger.info("Project lifecycle service shutting down")
            raise
        except Exception:
            logger.exception("Error in project lifecycle enforcement cycle")

        await asyncio.sleep(_CHECK_INTERVAL)

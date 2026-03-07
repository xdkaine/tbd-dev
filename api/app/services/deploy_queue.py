"""Deploy queue service.

Manages deploy ordering and concurrency limits per environment.
Ensures only N deploys run concurrently per environment (default 2)
and that deploys within an environment are processed in FIFO order.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.deploy import Deploy

logger = logging.getLogger(__name__)


async def enqueue_deploy(db: AsyncSession, deploy: Deploy) -> Deploy:
    """Enqueue a deploy and attempt to promote it immediately.

    If the environment has capacity (fewer than max_concurrent active deploys),
    the deploy transitions directly to its next state. Otherwise it stays
    queued and will be picked up when a slot opens.
    """
    # Check queue size limit
    queue_count = await _count_queued(db, deploy.env_id)
    if queue_count >= settings.deploy_queue_max_size:
        logger.warning(
            "Deploy queue full for env %s (%d/%d)",
            deploy.env_id,
            queue_count,
            settings.deploy_queue_max_size,
        )
        deploy.status = "failed"
        await db.flush()
        return deploy

    deploy.status = "queued"
    await db.flush()

    # Try to promote immediately if there's capacity
    await _try_promote_next(db, deploy.env_id)

    # Re-read to get potentially updated status
    await db.refresh(deploy)
    return deploy


async def on_deploy_completed(db: AsyncSession, env_id: uuid.UUID) -> None:
    """Called when a deploy reaches a terminal state (active, failed, rolled_back).

    Frees a concurrency slot and tries to promote the next queued deploy.
    """
    await _try_promote_next(db, env_id)


async def mark_superseded(
    db: AsyncSession, env_id: uuid.UUID, exclude_deploy_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Mark all currently active deploys in an environment as superseded.

    Called when a new deploy reaches the 'active' state — the previous
    active deploy should be marked superseded.

    Uses SELECT ... FOR UPDATE to lock the active rows so that two
    concurrent deploys reaching 'active' at the same time don't both
    try to supersede each other.

    Returns the list of deploy IDs that were marked superseded (so the
    caller can trigger teardown for each).
    """
    result = await db.execute(
        select(Deploy)
        .where(
            Deploy.env_id == env_id,
            Deploy.status == "active",
            Deploy.id != exclude_deploy_id,
        )
        .with_for_update()
    )
    superseded = result.scalars().all()
    superseded_ids: list[uuid.UUID] = []
    for deploy in superseded:
        if deploy.can_transition_to("superseded"):
            deploy.status = "superseded"
            superseded_ids.append(deploy.id)

    if superseded_ids:
        await db.flush()
        logger.info("Marked %d deploys as superseded in env %s", len(superseded_ids), env_id)

    return superseded_ids


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _count_queued(db: AsyncSession, env_id: uuid.UUID) -> int:
    """Count the number of queued deploys for an environment."""
    result = await db.execute(
        select(func.count()).where(
            Deploy.env_id == env_id,
            Deploy.status == "queued",
        )
    )
    return result.scalar() or 0


async def _count_in_progress(
    db: AsyncSession, env_id: uuid.UUID, *, lock: bool = False,
) -> int:
    """Count deploys that are actively being processed (not queued, not terminal).

    In-progress states: building, artifact_ready, provisioning, healthy.

    When *lock* is True the matching rows are locked with FOR UPDATE so
    that concurrent promoters serialise properly and cannot both see a
    stale count.
    """
    in_progress_states = ["building", "artifact_ready", "provisioning", "healthy"]
    if lock:
        # Lock the actual deploy rows to serialise concurrent checks.
        # We SELECT the rows first (FOR UPDATE), then count in Python.
        result = await db.execute(
            select(Deploy.id)
            .where(
                Deploy.env_id == env_id,
                Deploy.status.in_(in_progress_states),
            )
            .with_for_update()
        )
        return len(result.all())
    result = await db.execute(
        select(func.count()).where(
            Deploy.env_id == env_id,
            Deploy.status.in_(in_progress_states),
        )
    )
    return result.scalar() or 0


async def _try_promote_next(db: AsyncSession, env_id: uuid.UUID) -> bool:
    """Try to promote the next queued deploy if there is concurrency capacity.

    Uses SELECT … FOR UPDATE SKIP LOCKED so that concurrent callers each
    grab a *different* queued deploy (or none) rather than both grabbing
    the same row and double-promoting.

    Returns True if a deploy was promoted.
    """
    in_progress = await _count_in_progress(db, env_id)
    if in_progress >= settings.deploy_max_concurrent:
        logger.debug(
            "Env %s at concurrency limit (%d/%d)",
            env_id,
            in_progress,
            settings.deploy_max_concurrent,
        )
        return False

    # Get the oldest queued deploy (FIFO) with a row lock.
    # SKIP LOCKED ensures a concurrent call won't block on the same row —
    # it will either pick the *next* unlocked queued deploy or return None.
    result = await db.execute(
        select(Deploy)
        .where(Deploy.env_id == env_id, Deploy.status == "queued")
        .order_by(Deploy.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    next_deploy = result.scalar_one_or_none()

    if next_deploy is None:
        return False

    # Re-check concurrency after acquiring the lock to prevent over-promotion
    # when two callers both pass the initial count check simultaneously.
    # Use lock=True to serialise with other concurrent promoters.
    in_progress = await _count_in_progress(db, env_id, lock=True)
    if in_progress >= settings.deploy_max_concurrent:
        logger.debug(
            "Env %s at concurrency limit after lock (%d/%d) — not promoting",
            env_id,
            in_progress,
            settings.deploy_max_concurrent,
        )
        return False

    # Promote from queued -> building
    if next_deploy.can_transition_to("building"):
        next_deploy.status = "building"
        await db.flush()
        logger.info("Promoted deploy %s from queued to building", next_deploy.id)
        return True

    return False


async def get_queue_status(db: AsyncSession, env_id: uuid.UUID) -> dict:
    """Get the current queue status for an environment.

    Returns dict with counts of deploys in each state group.
    """
    queued = await _count_queued(db, env_id)
    in_progress = await _count_in_progress(db, env_id)

    active_result = await db.execute(
        select(func.count()).where(
            Deploy.env_id == env_id,
            Deploy.status == "active",
        )
    )
    active = active_result.scalar() or 0

    return {
        "env_id": str(env_id),
        "queued": queued,
        "in_progress": in_progress,
        "active": active,
        "max_concurrent": settings.deploy_max_concurrent,
        "max_queue_size": settings.deploy_queue_max_size,
    }

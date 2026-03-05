"""Aggregate quota enforcement.

Checks that a user's total resource usage across all projects does not
exceed the platform-wide per-user limits defined in settings.

Per-project quotas are managed by staff via the /quotas API. This module
enforces the *aggregate* ceiling so a single user cannot consume all
platform resources even if individual project quotas are generous.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.network import Quota
from app.models.project import Project

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Raised when a user would exceed their aggregate resource quota."""

    def __init__(self, resource: str, current: int, limit: int, unit: str = ""):
        self.resource = resource
        self.current = current
        self.limit = limit
        detail = f"User aggregate {resource} quota exceeded: using {current}{unit} of {limit}{unit} allowed"
        super().__init__(detail)


async def check_user_aggregate_quota(
    db: AsyncSession,
    owner_id: uuid.UUID,
    *,
    exclude_project_id: uuid.UUID | None = None,
) -> None:
    """Verify that the user hasn't exceeded aggregate resource limits.

    Sums cpu_limit, ram_limit, and disk_limit across all Quota rows
    belonging to the user's projects. Raises QuotaExceededError if any
    configured limit (> 0) would be exceeded.

    Args:
        db: Async database session.
        owner_id: The user whose projects to check.
        exclude_project_id: Optionally exclude a project (e.g. when
            recalculating after a quota update).
    """
    # If no aggregate limits are configured, skip entirely
    if (
        settings.user_max_cpu == 0
        and settings.user_max_ram_mb == 0
        and settings.user_max_disk_mb == 0
        and settings.user_max_projects == 0
    ):
        return

    # Count projects
    if settings.user_max_projects > 0:
        project_count_q = select(func.count(Project.id)).where(
            Project.owner_id == owner_id
        )
        if exclude_project_id:
            project_count_q = project_count_q.where(
                Project.id != exclude_project_id
            )
        result = await db.execute(project_count_q)
        project_count = result.scalar() or 0
        if project_count >= settings.user_max_projects:
            raise QuotaExceededError(
                "projects", project_count, settings.user_max_projects
            )

    # Sum resource quotas across all user's projects
    resource_q = (
        select(
            func.coalesce(func.sum(Quota.cpu_limit), 0).label("total_cpu"),
            func.coalesce(func.sum(Quota.ram_limit), 0).label("total_ram"),
            func.coalesce(func.sum(Quota.disk_limit), 0).label("total_disk"),
        )
        .join(Project, Project.id == Quota.project_id)
        .where(Project.owner_id == owner_id)
    )
    if exclude_project_id:
        resource_q = resource_q.where(
            Quota.project_id != exclude_project_id
        )

    result = await db.execute(resource_q)
    row = result.one()
    total_cpu = row.total_cpu
    total_ram = row.total_ram
    total_disk = row.total_disk

    if settings.user_max_cpu > 0 and total_cpu > settings.user_max_cpu:
        raise QuotaExceededError(
            "CPU", total_cpu, settings.user_max_cpu, " vCPUs"
        )

    if settings.user_max_ram_mb > 0 and total_ram > settings.user_max_ram_mb:
        raise QuotaExceededError(
            "RAM", total_ram, settings.user_max_ram_mb, "MB"
        )

    if settings.user_max_disk_mb > 0 and total_disk > settings.user_max_disk_mb:
        raise QuotaExceededError(
            "disk", total_disk, settings.user_max_disk_mb, "MB"
        )

    logger.debug(
        "Aggregate quota check passed for user %s: cpu=%d, ram=%dMB, disk=%dMB",
        owner_id, total_cpu, total_ram, total_disk,
    )

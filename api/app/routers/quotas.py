"""Quotas router - view and manage project resource quotas.

Staff can view quotas; Faculty can update them.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.network import Quota
from app.models.project import Project
from app.models.user import User
from app.schemas.quota import QuotaListResponse, QuotaResponse, QuotaUpdate, QuotaWithProject
from app.services.audit import write_audit_log
from app.services.rbac import check_permission

router = APIRouter(prefix="/admin/quotas", tags=["admin", "quotas"])


@router.get("", response_model=QuotaListResponse)
async def list_quotas(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, description="Search by project name"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all project quotas with project info.

    Requires quotas.read permission (Staff/Faculty).
    """
    check_permission(current_user.role, "quotas.read")

    # Build query joining Quota -> Project -> User (owner)
    query = (
        select(Quota, Project.name, Project.slug, User.username)
        .join(Project, Quota.project_id == Project.id)
        .join(User, Project.owner_id == User.id)
    )

    if search:
        query = query.where(Project.name.ilike(f"%{search}%"))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    # Fetch page
    result = await db.execute(
        query.order_by(Project.name).offset(skip).limit(limit)
    )
    rows = result.all()

    items = [
        QuotaWithProject(
            id=quota.id,
            project_id=quota.project_id,
            project_name=project_name,
            project_slug=project_slug,
            owner_username=owner_username,
            cpu_limit=quota.cpu_limit,
            ram_limit=quota.ram_limit,
            disk_limit=quota.disk_limit,
        )
        for quota, project_name, project_slug, owner_username in rows
    ]

    return QuotaListResponse(items=items, total=total)


@router.get("/{project_id}", response_model=QuotaResponse)
async def get_quota(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the quota for a specific project."""
    check_permission(current_user.role, "quotas.read")

    result = await db.execute(
        select(Quota).where(Quota.project_id == project_id)
    )
    quota = result.scalar_one_or_none()

    if quota is None:
        raise HTTPException(status_code=404, detail="Quota not found for this project")

    return QuotaResponse.model_validate(quota)


@router.patch("/{project_id}", response_model=QuotaResponse)
async def update_quota(
    project_id: uuid.UUID,
    body: QuotaUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the quota for a specific project (Faculty only)."""
    check_permission(current_user.role, "quotas.update")

    result = await db.execute(
        select(Quota).where(Quota.project_id == project_id)
    )
    quota = result.scalar_one_or_none()

    if quota is None:
        raise HTTPException(status_code=404, detail="Quota not found for this project")

    # Apply updates
    changes = {}
    if body.cpu_limit is not None:
        changes["cpu_limit"] = (quota.cpu_limit, body.cpu_limit)
        quota.cpu_limit = body.cpu_limit
    if body.ram_limit is not None:
        changes["ram_limit"] = (quota.ram_limit, body.ram_limit)
        quota.ram_limit = body.ram_limit
    if body.disk_limit is not None:
        changes["disk_limit"] = (quota.disk_limit, body.disk_limit)
        quota.disk_limit = body.disk_limit

    if changes:
        await write_audit_log(
            db,
            actor_user_id=current_user.id,
            action="quota.update",
            target_type="project",
            target_id=str(project_id),
            payload={k: {"from": v[0], "to": v[1]} for k, v in changes.items()},
        )
        await db.commit()
        await db.refresh(quota)

    return QuotaResponse.model_validate(quota)

"""Audit log router - read-only access to audit trail."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogListResponse, AuditLogResponse
from app.services.rbac import Role, check_permission

router = APIRouter(prefix="/audits", tags=["audits"])


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    action: str | None = Query(None, description="Filter by action type"),
    target_type: str | None = Query(None, description="Filter by target type"),
    actor_user_id: uuid.UUID | None = Query(None, description="Filter by actor"),
    since: datetime | None = Query(None, description="Filter entries after this time"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List audit log entries with optional filtering.

    Developers can only see their own audit entries.
    Staff and Faculty can see all entries.
    """
    check_permission(current_user.role, "audit.read")

    query = select(AuditLog)

    # Developers can only see their own audit entries
    if current_user.role == Role.DEVELOPER:
        query = query.where(AuditLog.actor_user_id == current_user.id)

    # Apply filters
    if action:
        query = query.where(AuditLog.action == action)
    if target_type:
        query = query.where(AuditLog.target_type == target_type)
    if actor_user_id and current_user.role != Role.DEVELOPER:
        query = query.where(AuditLog.actor_user_id == actor_user_id)
    if since:
        query = query.where(AuditLog.created_at >= since)

    # Count total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Fetch page
    result = await db.execute(
        query.offset(skip).limit(limit).order_by(AuditLog.created_at.desc())
    )
    entries = result.scalars().all()

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(e) for e in entries],
        total=total,
    )

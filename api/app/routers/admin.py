"""Admin router - platform statistics and overview for admin dashboard."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.build import Build
from app.models.deploy import Deploy
from app.models.network import Quota, Vlan
from app.models.network_policy import NetworkPolicy
from app.models.project import Project
from app.models.user import User
from app.services.rbac import check_permission

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminStats(BaseModel):
    """Platform-wide statistics for the admin dashboard."""

    total_users: int
    total_projects: int
    total_deploys: int
    active_deploys: int
    total_builds: int
    vlans_allocated: int
    vlans_available: int
    total_network_policies: int


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get platform-wide statistics for the admin dashboard.

    Requires audit.read permission (Staff/Faculty).
    """
    check_permission(current_user.role, "audit.read")

    # Run all count queries in parallel-ish fashion
    users_count = await db.execute(select(func.count(User.id)))
    projects_count = await db.execute(select(func.count(Project.id)))
    deploys_count = await db.execute(select(func.count(Deploy.id)))
    active_deploys_count = await db.execute(
        select(func.count(Deploy.id)).where(Deploy.status == "active")
    )
    builds_count = await db.execute(select(func.count(Build.id)))
    vlans_allocated_count = await db.execute(
        select(func.count(Vlan.id)).where(Vlan.reserved_by_project_id.isnot(None))
    )
    vlans_available_count = await db.execute(
        select(func.count(Vlan.id)).where(Vlan.reserved_by_project_id.is_(None))
    )
    policies_count = await db.execute(select(func.count(NetworkPolicy.id)))

    return AdminStats(
        total_users=users_count.scalar() or 0,
        total_projects=projects_count.scalar() or 0,
        total_deploys=deploys_count.scalar() or 0,
        active_deploys=active_deploys_count.scalar() or 0,
        total_builds=builds_count.scalar() or 0,
        vlans_allocated=vlans_allocated_count.scalar() or 0,
        vlans_available=vlans_available_count.scalar() or 0,
        total_network_policies=policies_count.scalar() or 0,
    )

"""Networks router - VLAN allocation and listing.

Delegates VLAN operations to the network_allocator service (M4).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.network import Vlan
from app.models.project import Project
from app.schemas.network import VlanListResponse, VlanReserveRequest, VlanResponse
from app.services.audit import write_audit_log
from app.services.network_allocator import (
    NetworkAllocationError,
    allocate_vlan,
    deallocate_vlan,
    get_project_vlan,
)
from app.services.rbac import check_permission

router = APIRouter(prefix="/networks", tags=["networks"])


@router.get("/vlans", response_model=VlanListResponse)
async def list_vlans(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all VLAN allocations."""
    check_permission(current_user.role, "networks.read")

    query = select(Vlan)
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(Vlan.vlan_tag))
    vlans = result.scalars().all()

    return VlanListResponse(
        items=[VlanResponse.model_validate(v) for v in vlans],
        total=total,
    )


@router.post("/vlans/reserve", response_model=VlanResponse, status_code=status.HTTP_201_CREATED)
async def reserve_vlan(
    body: VlanReserveRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reserve the next available VLAN for a project.

    Delegates to the network_allocator service which handles:
    - Allocation formula: VLAN tag = 1000 + N, subnet = 172.16.N.0/25
    - Idempotent: returns existing VLAN if already allocated
    """
    check_permission(current_user.role, "networks.reserve")

    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == body.project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        vlan = await allocate_vlan(db, body.project_id, current_user.id)
    except NetworkAllocationError as e:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=str(e),
        )

    return VlanResponse.model_validate(vlan)


@router.get("/vlans/{project_id}", response_model=VlanResponse)
async def get_vlan_for_project(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the VLAN allocation for a specific project."""
    check_permission(current_user.role, "networks.read")

    vlan = await get_project_vlan(db, project_id)
    if vlan is None:
        raise HTTPException(status_code=404, detail="No VLAN allocated for this project")

    return VlanResponse.model_validate(vlan)


@router.delete("/vlans/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def release_vlan(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Release a project's VLAN allocation (staff/faculty only)."""
    check_permission(current_user.role, "networks.reserve")

    released = await deallocate_vlan(db, project_id, current_user.id)
    if not released:
        raise HTTPException(status_code=404, detail="No VLAN allocated for this project")

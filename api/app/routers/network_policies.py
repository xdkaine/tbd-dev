"""Network policies router - manage project firewall rules.

Default posture is deny-all egress. Staff/Faculty create explicit
allow rules for legitimate traffic patterns.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.network_policy import NetworkPolicy
from app.models.project import Project
from app.schemas.network_policy import (
    NetworkPolicyCreate,
    NetworkPolicyListResponse,
    NetworkPolicyResponse,
    NetworkPolicyUpdate,
)
from app.services.audit import write_audit_log
from app.services.rbac import check_permission

router = APIRouter(prefix="/admin/network-policies", tags=["admin", "network-policies"])


@router.get("", response_model=NetworkPolicyListResponse)
async def list_network_policies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    project_id: uuid.UUID | None = Query(None, description="Filter by project"),
    direction: str | None = Query(None, description="Filter by direction (egress/ingress)"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List network policies across all projects.

    Requires networks.configure permission (Faculty) or networks.read (Staff).
    """
    check_permission(current_user.role, "networks.read")

    query = (
        select(NetworkPolicy, Project.name.label("project_name"))
        .join(Project, NetworkPolicy.project_id == Project.id)
    )

    if project_id:
        query = query.where(NetworkPolicy.project_id == project_id)
    if direction:
        query = query.where(NetworkPolicy.direction == direction)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    # Fetch page
    result = await db.execute(
        query.order_by(NetworkPolicy.created_at.desc()).offset(skip).limit(limit)
    )
    rows = result.all()

    items = [
        NetworkPolicyResponse(
            id=policy.id,
            project_id=policy.project_id,
            project_name=project_name,
            name=policy.name,
            direction=policy.direction,
            protocol=policy.protocol,
            port=policy.port,
            destination=policy.destination,
            action=policy.action,
            enabled=policy.enabled,
            created_at=policy.created_at,
        )
        for policy, project_name in rows
    ]

    return NetworkPolicyListResponse(items=items, total=total)


@router.post("", response_model=NetworkPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_network_policy(
    body: NetworkPolicyCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new network policy for a project.

    Requires networks.configure permission (Faculty only).
    """
    check_permission(current_user.role, "networks.configure")

    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == body.project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    policy = NetworkPolicy(
        project_id=body.project_id,
        name=body.name,
        direction=body.direction,
        protocol=body.protocol,
        port=body.port,
        destination=body.destination,
        action=body.action,
    )
    db.add(policy)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="network_policy.create",
        target_type="network_policy",
        target_id=str(policy.id),
        payload={
            "project_id": str(body.project_id),
            "name": body.name,
            "direction": body.direction,
            "destination": body.destination,
            "action": body.action,
        },
    )

    await db.commit()
    await db.refresh(policy)

    return NetworkPolicyResponse(
        id=policy.id,
        project_id=policy.project_id,
        project_name=project.name,
        name=policy.name,
        direction=policy.direction,
        protocol=policy.protocol,
        port=policy.port,
        destination=policy.destination,
        action=policy.action,
        enabled=policy.enabled,
        created_at=policy.created_at,
    )


@router.patch("/{policy_id}", response_model=NetworkPolicyResponse)
async def update_network_policy(
    policy_id: uuid.UUID,
    body: NetworkPolicyUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing network policy.

    Requires networks.configure permission (Faculty only).
    """
    check_permission(current_user.role, "networks.configure")

    result = await db.execute(select(NetworkPolicy).where(NetworkPolicy.id == policy_id))
    policy = result.scalar_one_or_none()

    if policy is None:
        raise HTTPException(status_code=404, detail="Network policy not found")

    # Get project name for response
    proj_result = await db.execute(select(Project.name).where(Project.id == policy.project_id))
    project_name = proj_result.scalar_one()

    changes = {}
    if body.name is not None:
        changes["name"] = (policy.name, body.name)
        policy.name = body.name
    if body.protocol is not None:
        changes["protocol"] = (policy.protocol, body.protocol)
        policy.protocol = body.protocol
    if body.port is not None:
        changes["port"] = (policy.port, body.port)
        policy.port = body.port
    if body.destination is not None:
        changes["destination"] = (policy.destination, body.destination)
        policy.destination = body.destination
    if body.action is not None:
        changes["action"] = (policy.action, body.action)
        policy.action = body.action
    if body.enabled is not None:
        changes["enabled"] = (policy.enabled, body.enabled)
        policy.enabled = body.enabled

    if changes:
        await write_audit_log(
            db,
            actor_user_id=current_user.id,
            action="network_policy.update",
            target_type="network_policy",
            target_id=str(policy_id),
            payload={k: {"from": str(v[0]), "to": str(v[1])} for k, v in changes.items()},
        )
        await db.commit()
        await db.refresh(policy)

    return NetworkPolicyResponse(
        id=policy.id,
        project_id=policy.project_id,
        project_name=project_name,
        name=policy.name,
        direction=policy.direction,
        protocol=policy.protocol,
        port=policy.port,
        destination=policy.destination,
        action=policy.action,
        enabled=policy.enabled,
        created_at=policy.created_at,
    )


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_network_policy(
    policy_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a network policy.

    Requires networks.configure permission (Faculty only).
    """
    check_permission(current_user.role, "networks.configure")

    result = await db.execute(select(NetworkPolicy).where(NetworkPolicy.id == policy_id))
    policy = result.scalar_one_or_none()

    if policy is None:
        raise HTTPException(status_code=404, detail="Network policy not found")

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="network_policy.delete",
        target_type="network_policy",
        target_id=str(policy_id),
        payload={"name": policy.name, "project_id": str(policy.project_id)},
    )

    await db.delete(policy)
    await db.commit()

"""Environments router - CRUD for project environments."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.environment import Environment
from app.models.project import Project
from app.schemas.environment import (
    EnvironmentCreate,
    EnvironmentListResponse,
    EnvironmentResponse,
)
from app.services.audit import write_audit_log
from app.services.rbac import Role, check_permission

router = APIRouter(prefix="/projects/{project_id}/environments", tags=["environments"])


async def _get_project_or_404(
    project_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession
) -> Project:
    """Helper to fetch project and check access."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=EnvironmentListResponse)
async def list_environments(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all environments for a project."""
    check_permission(current_user.role, "environments.read")
    await _get_project_or_404(project_id, current_user, db)

    query = select(Environment).where(Environment.project_id == project_id)
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(Environment.created_at.desc()))
    envs = result.scalars().all()

    return EnvironmentListResponse(
        items=[EnvironmentResponse.model_validate(e) for e in envs],
        total=total,
    )


@router.post("", response_model=EnvironmentResponse, status_code=status.HTTP_201_CREATED)
async def create_environment(
    project_id: uuid.UUID,
    body: EnvironmentCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new environment in a project."""
    check_permission(current_user.role, "environments.create")
    project = await _get_project_or_404(project_id, current_user, db)

    # Check for duplicate environment name within project
    existing = await db.execute(
        select(Environment).where(
            Environment.project_id == project_id,
            Environment.name == body.name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Environment '{body.name}' already exists in this project",
        )

    env = Environment(
        project_id=project_id,
        name=body.name,
        type=body.type,
    )
    db.add(env)
    await db.flush()

    # Audit
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="environment.create",
        target_type="environment",
        target_id=str(env.id),
        payload={
            "project_id": str(project_id),
            "name": body.name,
            "type": body.type,
        },
    )

    return EnvironmentResponse.model_validate(env)


@router.delete("/{env_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment(
    project_id: uuid.UUID,
    env_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an environment (staff/faculty only)."""
    check_permission(current_user.role, "environments.delete")
    await _get_project_or_404(project_id, current_user, db)

    result = await db.execute(
        select(Environment).where(
            Environment.id == env_id,
            Environment.project_id == project_id,
        )
    )
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")

    # Audit
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="environment.delete",
        target_type="environment",
        target_id=str(env.id),
        payload={"project_id": str(project_id), "name": env.name},
    )

    await db.delete(env)
    await db.flush()

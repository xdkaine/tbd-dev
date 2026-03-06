"""Projects router - CRUD operations for projects."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.deploy import Deploy
from app.models.environment import Environment
from app.models.network import Quota
from app.models.project import Project, ProjectMember
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.audit import write_audit_log
from app.services.deploy_teardown import teardown_deploy
from app.services.network_allocator import (
    auto_allocate_on_project_create,
    deallocate_vlan,
)
from app.services.rbac import Role, check_permission
from app.utils.project_access import is_project_contributor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects. Developers see their own + projects they contribute to."""
    check_permission(current_user.role, "projects.read")

    query = select(Project)

    # Developers see projects they own OR are a contributor on
    if current_user.role == Role.DEVELOPER:
        contributed_ids = (
            select(ProjectMember.project_id)
            .where(ProjectMember.user_id == current_user.id)
            .scalar_subquery()
        )
        query = query.where(
            or_(
                Project.owner_id == current_user.id,
                Project.id.in_(contributed_ids),
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Fetch page
    result = await db.execute(query.offset(skip).limit(limit).order_by(Project.created_at.desc()))
    projects = result.scalars().all()

    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=total,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project."""
    check_permission(current_user.role, "projects.create")

    # Check slug uniqueness
    existing = await db.execute(select(Project).where(Project.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project with slug '{body.slug}' already exists",
        )

    project = Project(
        name=body.name,
        slug=body.slug,
        repo_url=body.repo_url,
        owner_id=current_user.id,
        default_env=body.default_env,
    )
    db.add(project)
    await db.flush()

    # Create default environment
    default_env = Environment(
        project_id=project.id,
        name=body.default_env,
        type="production",
    )
    db.add(default_env)

    # Create default quota
    quota = Quota(project_id=project.id)
    db.add(quota)

    await db.flush()

    # Auto-allocate a VLAN for the project (M4 integration)
    try:
        await auto_allocate_on_project_create(db, project, current_user.id)
    except Exception as e:
        # VLAN allocation failure shouldn't block project creation
        import logging
        logging.getLogger(__name__).warning(
            "VLAN auto-allocation failed for project %s: %s", project.slug, e,
        )

    # Audit
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="project.create",
        target_type="project",
        target_id=str(project.id),
        payload={"name": body.name, "slug": body.slug},
    )

    # Refresh to load selectin relationships (repo, environments, etc.)
    # before Pydantic serialization — avoids MissingGreenlet in async context.
    await db.refresh(project)

    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a project by ID."""
    check_permission(current_user.role, "projects.read")

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Developers can see their own projects or projects they contribute to
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        if not await is_project_contributor(db, project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check permission - developers can update own or contributed projects
    if current_user.role == Role.DEVELOPER:
        check_permission(current_user.role, "projects.update")
        if project.owner_id != current_user.id:
            if not await is_project_contributor(db, project_id, current_user.id):
                raise HTTPException(status_code=403, detail="Cannot update another user's project")
    else:
        check_permission(current_user.role, "projects.update")

    # Apply updates
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.flush()

    # Audit
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="project.update",
        target_type="project",
        target_id=str(project.id),
        payload=update_data,
    )

    # Refresh to load selectin relationships (repo, environments, etc.)
    # before Pydantic serialization — avoids MissingGreenlet in async context.
    await db.refresh(project)

    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project. Developers can delete their own; staff/faculty can delete any.

    Before removing the database record this endpoint tears down all
    infrastructure associated with the project:
      1. Destroys LXC containers + Nginx configs for every deploy
      2. Releases the allocated VLAN (if any)
    """
    check_permission(current_user.role, "projects.delete")

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Developers can only delete their own projects
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's project")

    # Audit before deletion (while project still exists)
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="project.delete",
        target_type="project",
        target_id=str(project.id),
        payload={"name": project.name, "slug": project.slug},
    )

    # ── Infrastructure teardown ──────────────────────────────────────
    # Gather every deploy across all environments for this project that
    # still has infrastructure worth cleaning up.
    TEARDOWN_STATES = {"queued", "building", "artifact_ready", "provisioning",
                       "healthy", "active", "stopped", "failed"}

    env_ids_q = select(Environment.id).where(Environment.project_id == project_id)
    deploys_q = (
        select(Deploy)
        .where(
            Deploy.env_id.in_(env_ids_q),
            Deploy.status.in_(TEARDOWN_STATES),
        )
    )
    deploy_rows = await db.execute(deploys_q)
    deploys = deploy_rows.scalars().all()

    for deploy in deploys:
        is_active = deploy.status == "active"
        try:
            await teardown_deploy(
                db,
                deploy.id,
                remove_production_route=is_active,
                destroy_container=True,
            )
        except Exception as exc:
            # Log but don't abort – best-effort cleanup; the DB cascade
            # will still remove the rows so we won't leave ghost records.
            logger.warning(
                "Teardown failed for deploy %s during project delete: %s",
                str(deploy.id)[:8], exc,
            )

    # If no deploy was active but the project still has a production Nginx
    # config on disk, clean it up explicitly.
    if not any(d.status == "active" for d in deploys):
        try:
            from app.services.dns_routing import (
                signal_nginx_reload,
                unregister_production_routing,
            )
            removed = await unregister_production_routing(project.slug)
            if removed:
                await signal_nginx_reload()
        except Exception as exc:
            logger.warning(
                "Failed to remove stale production route for %s: %s",
                project.slug, exc,
            )

    # ── Release VLAN ─────────────────────────────────────────────────
    try:
        await deallocate_vlan(db, project_id, actor_user_id=current_user.id)
    except Exception as exc:
        logger.warning(
            "VLAN deallocation failed for project %s: %s", project.slug, exc,
        )

    # ── Delete project (cascades to environments, deploys, etc.) ─────
    await db.delete(project)
    await db.flush()

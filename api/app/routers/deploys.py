"""Deploys router - create deploys, rollback, destroy, start/stop containers.

M2 additions:
- Deploy queue integration with concurrency limits
- State transition endpoint (PATCH /deploys/{id}/status)
- Queue status endpoint (GET /environments/{id}/queue)

M3 additions:
- Deploy logs REST endpoint (GET /projects/{id}/deploys/{deploy_id}/logs)
- Deploy logs SSE stream (GET /projects/{id}/deploys/{deploy_id}/logs/stream)

Deploy rework additions:
- Rollback: finds last successful deploy for env, redeploys; if none, tears down
- Destroy: DELETE /deploys/{id} — full infrastructure teardown
- Start/Stop: POST /deploys/{id}/start, POST /deploys/{id}/stop
- Container limit: max 3 running containers per project, returns 409 if exceeded
"""

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user, get_current_user_from_token
from app.models.build import Artifact, Build
from app.models.deploy import Deploy
from app.models.environment import Environment
from app.models.project import Project
from app.schemas.deploy import (
    DeployCreate,
    DeployListResponse,
    DeployLogsResponse,
    DeployResponse,
    RollbackRequest,
)
from app.services.audit import write_audit_log
from app.services.build_coordinator import transition_deploy, trigger_deploy
from app.services.deploy_queue import enqueue_deploy, get_queue_status
from app.services.rbac import Role, check_permission, has_permission
from app.utils.project_access import is_project_contributor
from app.utils.dns import deploy_url

router = APIRouter(tags=["deploys"])

# Max running (active or superseded-with-container) deploys per project.
# Users must stop one before deploying if at the limit.
MAX_RUNNING_PER_PROJECT = 3


# ---------------------------------------------------------------------------
# M2 schemas
# ---------------------------------------------------------------------------


class DeployStatusUpdate(BaseModel):
    """Request to transition a deploy to a new state."""

    status: str = Field(..., description="New deploy status")
    description: str = Field("", max_length=1024)


class QueueStatusResponse(BaseModel):
    """Deploy queue status for an environment."""

    env_id: str
    queued: int
    in_progress: int
    active: int
    max_concurrent: int
    max_queue_size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_project_for_deploy(
    db: AsyncSession,
    deploy: Deploy,
) -> Project:
    """Walk deploy -> environment -> project to get the owning project."""
    env_result = await db.execute(
        select(Environment)
        .where(Environment.id == deploy.env_id)
        .options(
            selectinload(Environment.project).selectinload(Project.owner)
        )
    )
    environment = env_result.scalar_one_or_none()
    if environment is None or environment.project is None:
        raise HTTPException(status_code=404, detail="Project not found for deploy")
    return environment.project


async def _check_ownership(
    db: AsyncSession,
    current_user: CurrentUser,
    project: Project,
    permission: str,
) -> None:
    """Check if the user has the permission OR the .own variant + ownership/contributor.

    For Staff/Faculty with the full permission, this is a no-op.
    For Developers with only the .own variant, verifies they own the project
    or are a contributor on it.
    """
    # If they have the full (non-.own) permission, allow
    if has_permission(current_user.role, permission):
        return

    # Check .own variant
    own_perm = f"{permission}.own"
    if has_permission(current_user.role, own_perm):
        if project.owner_id == current_user.id:
            return
        # Also allow contributors
        if await is_project_contributor(db, project.id, current_user.id):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only perform this action on your own projects",
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Insufficient permissions: '{permission}' required",
    )


def _deploy_to_response(deploy: Deploy, production_deploy_id: uuid.UUID | None = None) -> DeployResponse:
    """Build a DeployResponse with is_production and build info computed."""
    resp = DeployResponse.model_validate(deploy)
    resp.is_production = (deploy.id == production_deploy_id) if production_deploy_id else False
    # Populate build info from artifact → build chain
    artifact = getattr(deploy, "artifact", None)
    if artifact is not None:
        resp.build_id = artifact.build_id
        build = getattr(artifact, "build", None)
        if build is not None:
            resp.commit_sha = build.commit_sha
    return resp


async def _get_production_deploy_id(
    db: AsyncSession, project: Project,
) -> uuid.UUID | None:
    """Get the deploy ID that currently holds the production URL for a project.

    The production deploy is the most recently promoted active deploy in the
    project's default (production) environment.
    """
    env_result = await db.execute(
        select(Environment.id).where(Environment.project_id == project.id)
    )
    env_ids = [row[0] for row in env_result.all()]
    if not env_ids:
        return None

    result = await db.execute(
        select(Deploy.id)
        .where(
            Deploy.env_id.in_(env_ids),
            Deploy.status == "active",
        )
        .order_by(Deploy.promoted_at.desc().nullslast())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row


async def _count_running_deploys(
    db: AsyncSession, project_id: uuid.UUID, *, lock: bool = False,
) -> int:
    """Count deploys with a running container (active or superseded with container).

    When *lock* is True, the matching deploy rows are locked with FOR UPDATE
    to serialise concurrent container-limit checks for the same project.
    """
    env_result = await db.execute(
        select(Environment.id).where(Environment.project_id == project_id)
    )
    env_ids = [row[0] for row in env_result.all()]
    if not env_ids:
        return 0

    query = select(func.count()).where(
        Deploy.env_id.in_(env_ids),
        Deploy.status.in_(["active", "superseded"]),
        Deploy.container_vmid.isnot(None),
    )

    if lock:
        # Lock the actual rows to prevent concurrent callers from both
        # seeing a count below the limit.
        locked_result = await db.execute(
            select(Deploy.id)
            .where(
                Deploy.env_id.in_(env_ids),
                Deploy.status.in_(["active", "superseded"]),
                Deploy.container_vmid.isnot(None),
            )
            .with_for_update()
        )
        return len(locked_result.all())

    result = await db.execute(query)
    return result.scalar() or 0


async def _check_container_limit(
    db: AsyncSession,
    project_id: uuid.UUID,
    exclude_deploy_id: uuid.UUID | None = None,
) -> None:
    """Raise HTTP 409 if the project already has MAX_RUNNING_PER_PROJECT containers.

    Args:
        project_id: Project UUID.
        exclude_deploy_id: Deploy to exclude from the count (e.g. a stopped
            deploy that is about to be restarted — it's already counted if
            it has a container_vmid, but since it's stopped it won't be in
            the active/superseded query).

    Raises:
        HTTPException(409) when the limit would be exceeded.
    """
    running = await _count_running_deploys(db, project_id, lock=True)
    if running >= MAX_RUNNING_PER_PROJECT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Container limit reached: {running}/{MAX_RUNNING_PER_PROJECT} "
                f"running deploys for this project. Stop or destroy an existing "
                f"deploy before starting a new one."
            ),
        )


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/deploys", response_model=DeployListResponse)
async def list_deploys(
    project_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List deploys for a project across all environments."""
    check_permission(current_user.role, "deploys.read")

    # Verify project access
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        if not await is_project_contributor(db, project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Project not found")

    # Get all environment IDs for this project
    env_result = await db.execute(
        select(Environment.id).where(Environment.project_id == project_id)
    )
    env_ids = [row[0] for row in env_result.all()]

    if not env_ids:
        return DeployListResponse(items=[], total=0)

    query = select(Deploy).where(Deploy.env_id.in_(env_ids)).options(
        selectinload(Deploy.artifact).selectinload(Artifact.build)
    )
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(Deploy.created_at.desc())
    )
    deploys = result.scalars().all()

    prod_deploy_id = await _get_production_deploy_id(db, project)

    return DeployListResponse(
        items=[_deploy_to_response(d, prod_deploy_id) for d in deploys],
        total=total,
    )


@router.post(
    "/projects/{project_id}/deploys",
    response_model=DeployResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_deploy(
    project_id: uuid.UUID,
    body: DeployCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new deployment.

    This is the direct deploy endpoint (bypassing the build pipeline).
    For normal GitHub-triggered deploys, use the build router's
    POST /projects/{id}/builds/{build_id}/deploy endpoint instead.

    Deploys are enqueued and subject to concurrency limits per environment.
    """
    check_permission(current_user.role, "deploys.create")

    # Verify project exists
    proj_result = await db.execute(
        select(Project).where(Project.id == project_id).options(selectinload(Project.owner))
    )
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Find the target environment
    env_result = await db.execute(
        select(Environment).where(
            Environment.project_id == project_id,
            Environment.name == body.env,
        )
    )
    environment = env_result.scalar_one_or_none()

    # Auto-create preview environments for PRs
    if environment is None and body.env.startswith("pr-"):
        environment = Environment(
            project_id=project_id,
            name=body.env,
            type="preview",
        )
        db.add(environment)
        await db.flush()
    elif environment is None:
        raise HTTPException(
            status_code=404,
            detail=f"Environment '{body.env}' not found. Create it first.",
        )

    # Generate URL: <deployid>-<username>.dev.sdc.cpp
    deploy = Deploy(
        env_id=environment.id,
        status="queued",
    )
    db.add(deploy)
    await db.flush()  # Assigns deploy.id

    owner_username = project.owner.username if project.owner else "unknown"
    url = deploy_url(deploy.id, owner_username)
    deploy.url = url

    # Enqueue with concurrency control
    deploy = await enqueue_deploy(db, deploy)

    # Audit
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="deploy.create",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={
            "project_id": str(project_id),
            "env": body.env,
            "image_ref": body.image_ref,
        },
    )

    return DeployResponse.model_validate(deploy)


# ---------------------------------------------------------------------------
# M2: State transitions
# ---------------------------------------------------------------------------


@router.patch("/deploys/{deploy_id}/status", response_model=DeployResponse)
async def update_deploy_status(
    deploy_id: uuid.UUID,
    body: DeployStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transition a deploy to a new state.

    Used by the runtime plane (M3) to report deploy progress:
    - building -> artifact_ready -> provisioning -> healthy -> active
    - Any state -> failed (on error)

    Validates transitions against the deploy state machine.
    """
    check_permission(current_user.role, "deploys.create")

    try:
        deploy = await transition_deploy(
            db,
            deploy_id=deploy_id,
            new_status=body.status,
            description=body.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DeployResponse.model_validate(deploy)


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


@router.post("/deploys/{deploy_id}/rollback", response_model=DeployResponse)
async def rollback_deploy(
    deploy_id: uuid.UUID,
    body: RollbackRequest | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rollback a deployment.

    Finds the previous superseded/stopped deploy for the same environment
    that still has a running container, and re-promotes it to the production
    URL. No new build or deploy is created.

    If no previous deploy with a live container exists, performs a full
    teardown and removes the production URL.

    The current deploy is transitioned to 'superseded' (container stays alive).
    """
    check_permission(current_user.role, "deploys.rollback")

    # Load the deploy with a row lock to prevent concurrent rollbacks
    # from both reading the same deploy as 'active'.
    result = await db.execute(
        select(Deploy).where(Deploy.id == deploy_id).with_for_update()
    )
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise HTTPException(status_code=404, detail="Deploy not found")

    # Ownership check for .own permissions
    project = await _get_project_for_deploy(db, deploy)
    await _check_ownership(db, current_user, project, "deploys.rollback")

    # Must be active to rollback
    if deploy.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot rollback deploy in state '{deploy.status}'. Only active deploys can be rolled back.",
        )

    reason = body.reason if body and body.reason else "Manual rollback"

    # Find the previous deploy that still has a live container
    # (superseded or stopped, with container_vmid set)
    # Lock the candidate row to prevent a concurrent rollback from
    # re-promoting the same deploy simultaneously.
    prev_result = await db.execute(
        select(Deploy)
        .where(
            Deploy.env_id == deploy.env_id,
            Deploy.id != deploy_id,
            Deploy.status.in_(["superseded", "stopped"]),
            Deploy.container_vmid.isnot(None),
            Deploy.container_ip.isnot(None),
        )
        .order_by(Deploy.promoted_at.desc().nullslast(), Deploy.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    previous_deploy = prev_result.scalar_one_or_none()

    # Mark current deploy as superseded (keep container alive)
    deploy.status = "superseded"
    await db.flush()

    if previous_deploy:
        # Re-promote the previous deploy
        previous_deploy.status = "active"
        previous_deploy.promoted_at = datetime.now(timezone.utc)
        await db.flush()

        # Switch production Nginx config to the previous deploy's container
        from app.services.dns_routing import register_production_routing
        from app.utils.dns import production_url as make_production_url
        owner_username = project.owner.username if project.owner else "unknown"
        backend_port = previous_deploy.container_port or 3000

        try:
            await register_production_routing(
                project_slug=project.slug,
                owner_username=owner_username,
                backend_ip=previous_deploy.container_ip,
                backend_port=backend_port,
                deploy_id=str(previous_deploy.id),
            )
            project.production_url = make_production_url(project.slug, owner_username)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to switch production routing during rollback: %s", e,
            )

        await write_audit_log(
            db,
            actor_user_id=current_user.id,
            action="deploy.rollback.repromote",
            target_type="deploy",
            target_id=str(deploy.id),
            payload={
                "reason": reason,
                "repromoted_deploy_id": str(previous_deploy.id),
            },
        )
        await db.commit()
        return DeployResponse.model_validate(deploy)

    # No previous deploy with live container — remove production URL
    from app.services.dns_routing import unregister_production_routing
    await unregister_production_routing(project.slug)
    project.production_url = None

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="deploy.rollback.teardown",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={"reason": reason, "action": "no_previous_deploy"},
    )
    await db.commit()

    return DeployResponse.model_validate(deploy)


# ---------------------------------------------------------------------------
# Promote (set as production URL)
# ---------------------------------------------------------------------------


@router.post("/deploys/{deploy_id}/promote", response_model=DeployResponse)
async def promote_deploy(
    deploy_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Promote a deploy to the production URL.

    Switches the production Nginx config to point to this deploy's container.
    The previously active deploy is marked 'superseded' but its container
    and per-deploy URL remain alive.

    Can be called on:
    - 'active' deploys that aren't already the production deploy
    - 'superseded' deploys (re-promote a previous deploy)
    """
    check_permission(current_user.role, "deploys.create")

    result = await db.execute(
        select(Deploy).where(Deploy.id == deploy_id).with_for_update()
    )
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise HTTPException(status_code=404, detail="Deploy not found")

    project = await _get_project_for_deploy(db, deploy)
    await _check_ownership(db, current_user, project, "deploys.create")

    # Must be active or superseded (has a running container)
    if deploy.status not in ("active", "superseded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot promote deploy in state '{deploy.status}'. "
                   f"Only active or superseded deploys can be promoted.",
        )

    # Must have a container running
    if not deploy.container_ip or not deploy.container_vmid:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deploy has no running container. Cannot promote.",
        )

    # Check if already the production deploy
    prod_id = await _get_production_deploy_id(db, project)
    if prod_id == deploy.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This deploy is already the production deploy.",
        )

    # Mark current active deploys as superseded (keep containers alive)
    from app.services.deploy_queue import mark_superseded
    superseded_ids = await mark_superseded(db, deploy.env_id, deploy.id)

    # Transition this deploy to active
    deploy.status = "active"
    deploy.promoted_at = datetime.now(timezone.utc)
    await db.flush()

    # Update production Nginx config to point to this deploy's container
    from app.services.dns_routing import register_production_routing
    owner_username = project.owner.username if project.owner else "unknown"
    backend_port = deploy.container_port or 3000

    try:
        await register_production_routing(
            project_slug=project.slug,
            owner_username=owner_username,
            backend_ip=deploy.container_ip,
            backend_port=backend_port,
            deploy_id=str(deploy.id),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update production routing: {e}",
        )

    # Update project's production URL
    from app.utils.dns import production_url
    project.production_url = production_url(project.slug, owner_username)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="deploy.promote",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={
            "project_id": str(project.id),
            "superseded_ids": [str(sid) for sid in superseded_ids],
        },
    )
    await db.commit()

    return _deploy_to_response(deploy, deploy.id)


# ---------------------------------------------------------------------------
# Destroy
# ---------------------------------------------------------------------------


@router.delete("/deploys/{deploy_id}", response_model=DeployResponse)
async def destroy_deploy(
    deploy_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Destroy a deployment — full infrastructure teardown.

    Stops and destroys the LXC container, removes Nginx config, clears URL.
    The deploy is transitioned to 'rolled_back' (terminal state).

    Can be called on any non-terminal deploy (active, stopped, failed, etc.).
    """
    check_permission(current_user.role, "deploys.destroy")

    result = await db.execute(select(Deploy).where(Deploy.id == deploy_id))
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise HTTPException(status_code=404, detail="Deploy not found")

    # Ownership check
    project = await _get_project_for_deploy(db, deploy)
    await _check_ownership(db, current_user, project, "deploys.destroy")

    # Already terminal?
    if deploy.status == "rolled_back":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deploy is already destroyed (rolled_back)",
        )

    # Check if this is the active production deploy
    is_active = deploy.status == "active"

    # Teardown infrastructure
    from app.services.deploy_teardown import teardown_deploy
    await teardown_deploy(
        db,
        deploy_id,
        remove_production_route=is_active,  # only remove production route if this was active
        destroy_container=True,
    )

    # Transition to rolled_back (terminal)
    if deploy.can_transition_to("rolled_back"):
        deploy.status = "rolled_back"
    else:
        # Force to rolled_back for states that don't normally transition
        # (e.g., failed, building, etc.)
        deploy.status = "rolled_back"

    if is_active:
        project.production_url = None

    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="deploy.destroy",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={"was_active": is_active},
    )
    await db.commit()

    return DeployResponse.model_validate(deploy)


# ---------------------------------------------------------------------------
# Start / Stop containers
# ---------------------------------------------------------------------------


@router.post("/deploys/{deploy_id}/stop", response_model=DeployResponse)
async def stop_deploy(
    deploy_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop a running deploy's container without destroying it.

    The container is stopped on Proxmox but not destroyed.
    Per-deploy Nginx routing is removed so traffic stops flowing.
    The deploy transitions to 'stopped'.
    Can be restarted later with POST /deploys/{id}/start.
    """
    check_permission(current_user.role, "deploys.container")

    result = await db.execute(select(Deploy).where(Deploy.id == deploy_id))
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise HTTPException(status_code=404, detail="Deploy not found")

    project = await _get_project_for_deploy(db, deploy)
    await _check_ownership(db, current_user, project, "deploys.container")

    if deploy.status not in ("active", "superseded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Can only stop active or superseded deploys (current: '{deploy.status}')",
        )

    was_production = False
    prod_id = await _get_production_deploy_id(db, project)
    if prod_id == deploy.id:
        was_production = True

    # Stop the LXC container (don't destroy it) — use stored VMID
    from app.services.deploy_teardown import stop_lxc_container
    from app.services.proxmox_adapter import get_proxmox_adapter
    from app.services.dns_routing import unregister_deploy_routing, unregister_production_routing

    adapter = get_proxmox_adapter()

    if deploy.container_vmid and deploy.container_node:
        await stop_lxc_container(adapter, deploy.container_node, deploy.container_vmid)

    # Remove per-deploy Nginx routing (traffic should stop)
    await unregister_deploy_routing(str(deploy_id))

    # If this was the production deploy, also remove production routing
    if was_production:
        await unregister_production_routing(project.slug)
        project.production_url = None

    # Transition to stopped
    deploy.status = "stopped"
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="deploy.stop",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={"was_production": was_production},
    )
    await db.commit()

    return DeployResponse.model_validate(deploy)


@router.post("/deploys/{deploy_id}/start", response_model=DeployResponse)
async def start_deploy(
    deploy_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restart a stopped deploy's container.

    Re-starts the LXC container on Proxmox, re-registers Nginx routing,
    and transitions the deploy back to 'active'.

    Subject to the per-project container limit (max 3 running).
    If the limit would be exceeded, the oldest active container
    in the project is automatically stopped to make room.
    """
    check_permission(current_user.role, "deploys.container")

    result = await db.execute(select(Deploy).where(Deploy.id == deploy_id))
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise HTTPException(status_code=404, detail="Deploy not found")

    project = await _get_project_for_deploy(db, deploy)
    await _check_ownership(db, current_user, project, "deploys.container")

    if deploy.status != "stopped":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Can only start stopped deploys (current: '{deploy.status}')",
        )

    # Enforce container limit — raises 409 if at capacity
    await _check_container_limit(db, project.id)

    # Start the LXC container
    from app.services.deploy_teardown import _find_lxc_for_deploy
    from app.services.proxmox_adapter import get_proxmox_adapter, ProxmoxError
    from app.services.dns_routing import register_deploy_routing

    adapter = get_proxmox_adapter()

    env_result = await db.execute(select(Environment).where(Environment.id == deploy.env_id))
    environment = env_result.scalar_one_or_none()
    hostname = f"{project.slug}-{environment.name}" if environment else ""

    if hostname:
        lxc = await _find_lxc_for_deploy(adapter, hostname)
        if lxc:
            node, vmid = lxc
            try:
                start_upid = await adapter.start_lxc(node, vmid)
                if start_upid:
                    await adapter.wait_for_task(node, start_upid, timeout=60.0)
            except ProxmoxError as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to start container: {e}",
                )

            # Re-register Nginx routing
            owner_username = project.owner.username if project.owner else "unknown"
            # We need the container IP — get it from the config
            try:
                config = await adapter.get_lxc_config(node, vmid)
                net0 = config.get("net0", "")
                ip_addr = None
                for part in net0.split(","):
                    if part.strip().startswith("ip="):
                        ip_addr = part.strip()[3:].split("/")[0]
                        break
                if ip_addr:
                    await register_deploy_routing(
                        deploy_id=str(deploy_id),
                        owner_username=owner_username,
                        backend_ip=ip_addr,
                        backend_port=3000,  # Default app port
                    )
            except Exception as e:
                # Non-fatal: container is running but routing may not work yet
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to re-register routing for deploy %s: %s", deploy_id, e,
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Container not found on Proxmox (hostname: {hostname}). It may have been destroyed.",
            )

    # Transition back to active
    deploy.status = "active"
    deploy.promoted_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="deploy.start",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={},
    )
    await db.commit()

    return DeployResponse.model_validate(deploy)


# ---------------------------------------------------------------------------
# M2: Queue status
# ---------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/environments/{env_id}/queue",
    response_model=QueueStatusResponse,
)
async def get_environment_queue_status(
    project_id: uuid.UUID,
    env_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the deploy queue status for an environment.

    Shows how many deploys are queued, in progress, and active, along
    with the configured concurrency limits.
    """
    check_permission(current_user.role, "deploys.read")

    # Verify environment belongs to project
    env_result = await db.execute(
        select(Environment).where(
            Environment.id == env_id,
            Environment.project_id == project_id,
        )
    )
    environment = env_result.scalar_one_or_none()
    if environment is None:
        raise HTTPException(status_code=404, detail="Environment not found")

    queue = await get_queue_status(db, env_id)
    return QueueStatusResponse(**queue)


# ---------------------------------------------------------------------------
# Deploy logs
# ---------------------------------------------------------------------------

TERMINAL_DEPLOY_STATUSES = frozenset(
    ["active", "failed", "rolled_back", "superseded", "stopped"]
)


@router.get(
    "/projects/{project_id}/deploys/{deploy_id}/logs",
    response_model=DeployLogsResponse,
)
async def get_deploy_logs(
    project_id: uuid.UUID,
    deploy_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get deploy logs for a specific deploy.

    Returns the deploy status and log output from the deploy pipeline.
    """
    check_permission(current_user.role, "deploys.read")

    # Verify project access
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        if not await is_project_contributor(db, project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Project not found")

    # Find deploy (must belong to an environment of this project)
    env_result = await db.execute(
        select(Environment.id).where(Environment.project_id == project_id)
    )
    env_ids = [row[0] for row in env_result.all()]

    result = await db.execute(
        select(Deploy).where(Deploy.id == deploy_id, Deploy.env_id.in_(env_ids))
    )
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise HTTPException(status_code=404, detail="Deploy not found")

    return DeployLogsResponse(
        deploy_id=deploy.id,
        status=deploy.status,
        logs=deploy.logs,
    )


@router.get("/projects/{project_id}/deploys/{deploy_id}/logs/stream")
async def stream_deploy_logs(
    project_id: uuid.UUID,
    deploy_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Stream deploy logs via Server-Sent Events.

    Polls the database every 500ms and sends new log content as SSE events.
    Automatically closes when the deploy reaches a terminal state.

    Event types:
    - `log`: partial log payload with `logs` (full text) and `status`
    - `done`: final event when the deploy has finished
    """
    check_permission(current_user.role, "deploys.read")

    # Verify project access
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        if not await is_project_contributor(db, project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Project not found")

    # Verify deploy belongs to project
    env_result = await db.execute(
        select(Environment.id).where(Environment.project_id == project_id)
    )
    env_ids = [row[0] for row in env_result.all()]

    result = await db.execute(
        select(Deploy).where(Deploy.id == deploy_id, Deploy.env_id.in_(env_ids))
    )
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise HTTPException(status_code=404, detail="Deploy not found")

    async def event_generator():
        """Yield SSE events as the deploy progresses."""
        import json
        import time

        from app.config import settings

        last_len = 0
        last_heartbeat = time.monotonic()
        started_at = time.monotonic()
        max_duration = settings.sse_stream_timeout_seconds

        while True:
            # Refresh deploy from DB to get latest logs
            await db.refresh(deploy)

            current_logs = deploy.logs or ""
            current_status = deploy.status

            # Send update if logs have grown
            if len(current_logs) > last_len:
                data = json.dumps({
                    "logs": current_logs,
                    "status": current_status,
                })
                yield f"event: log\ndata: {data}\n\n"
                last_len = len(current_logs)
                last_heartbeat = time.monotonic()

            # If deploy reached a terminal state, send final event and close
            if current_status in TERMINAL_DEPLOY_STATUSES:
                data = json.dumps({
                    "logs": current_logs,
                    "status": current_status,
                })
                yield f"event: done\ndata: {data}\n\n"
                return

            # Enforce max stream duration
            elapsed = time.monotonic() - started_at
            if elapsed >= max_duration:
                data = json.dumps({
                    "reason": "stream_timeout",
                    "elapsed_seconds": int(elapsed),
                    "status": current_status,
                })
                yield f"event: timeout\ndata: {data}\n\n"
                return

            # Send keepalive comment every 15s to prevent proxy/CDN timeouts
            now = time.monotonic()
            if now - last_heartbeat >= 15:
                yield ": keepalive\n\n"
                last_heartbeat = now

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

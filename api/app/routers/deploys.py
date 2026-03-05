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
- Container limit: max 3 running containers per project, auto-stops excess
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
from app.utils.dns import deploy_url

router = APIRouter(tags=["deploys"])

# Max running (active or stopped-but-startable) containers per project.
# Users can start/stop within this limit — starting one may auto-stop another.
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
        .options(selectinload(Environment.project))
    )
    environment = env_result.scalar_one_or_none()
    if environment is None or environment.project is None:
        raise HTTPException(status_code=404, detail="Project not found for deploy")
    return environment.project


def _check_ownership(
    current_user: CurrentUser,
    project: Project,
    permission: str,
) -> None:
    """Check if the user has the permission OR the .own variant + ownership.

    For Staff/Faculty with the full permission, this is a no-op.
    For Developers with only the .own variant, verifies they own the project.
    """
    # If they have the full (non-.own) permission, allow
    if has_permission(current_user.role, permission):
        return

    # Check .own variant
    own_perm = f"{permission}.own"
    if has_permission(current_user.role, own_perm):
        if project.owner_id == current_user.id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only perform this action on your own projects",
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Insufficient permissions: '{permission}' required",
    )


async def _enforce_container_limit(
    db: AsyncSession,
    project_id: uuid.UUID,
    exclude_deploy_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Ensure at most MAX_RUNNING_PER_PROJECT containers are running for a project.

    If there are already MAX_RUNNING_PER_PROJECT active containers and we need
    to start another one, this stops the oldest active containers to make room.

    Args:
        project_id: Project UUID.
        exclude_deploy_id: Deploy to exclude from stopping (the one being started).

    Returns:
        List of deploy IDs that were stopped to make room.
    """
    # Find all environments for this project
    env_result = await db.execute(
        select(Environment.id).where(Environment.project_id == project_id)
    )
    env_ids = [row[0] for row in env_result.all()]
    if not env_ids:
        return []

    # Find all active (running) deploys for this project, oldest first
    active_query = (
        select(Deploy)
        .where(
            Deploy.env_id.in_(env_ids),
            Deploy.status == "active",
        )
        .order_by(Deploy.promoted_at.asc().nullslast(), Deploy.created_at.asc())
    )
    result = await db.execute(active_query)
    active_deploys = list(result.scalars().all())

    # Filter out the deploy we're about to start
    if exclude_deploy_id:
        candidates = [d for d in active_deploys if d.id != exclude_deploy_id]
    else:
        candidates = active_deploys

    # How many need to be stopped?
    # After starting the new one, total running = len(active_deploys) + (1 if exclude_deploy_id else 0)
    total_after = len(active_deploys) + (1 if exclude_deploy_id and exclude_deploy_id not in [d.id for d in active_deploys] else 0)
    excess = total_after - MAX_RUNNING_PER_PROJECT
    if excess <= 0:
        return []

    # Stop the oldest excess containers
    stopped_ids: list[uuid.UUID] = []
    from app.services.deploy_teardown import stop_lxc_container, _find_lxc_for_deploy
    from app.services.proxmox_adapter import get_proxmox_adapter

    adapter = get_proxmox_adapter()

    for deploy in candidates[:excess]:
        # Get hostname for this deploy
        env_res = await db.execute(
            select(Environment)
            .where(Environment.id == deploy.env_id)
            .options(selectinload(Environment.project))
        )
        env = env_res.scalar_one_or_none()
        if not env or not env.project:
            continue

        hostname = f"{env.project.slug}-{env.name}"
        lxc = await _find_lxc_for_deploy(adapter, hostname)
        if lxc:
            node, vmid = lxc
            await stop_lxc_container(adapter, node, vmid)

        # Transition to stopped
        deploy.status = "stopped"
        await db.flush()
        stopped_ids.append(deploy.id)

    return stopped_ids


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
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all environment IDs for this project
    env_result = await db.execute(
        select(Environment.id).where(Environment.project_id == project_id)
    )
    env_ids = [row[0] for row in env_result.all()]

    if not env_ids:
        return DeployListResponse(items=[], total=0)

    query = select(Deploy).where(Deploy.env_id.in_(env_ids))
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(Deploy.created_at.desc())
    )
    deploys = result.scalars().all()

    return DeployListResponse(
        items=[DeployResponse.model_validate(d) for d in deploys],
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
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
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

    Finds the last successful deploy for the same environment and redeploys
    that artifact. If no previous successful deploy exists, tears down all
    infrastructure (destroys LXC, removes Nginx config, clears URL).

    The current deploy is transitioned to 'rolled_back'.
    """
    check_permission(current_user.role, "deploys.rollback")

    # Load the deploy
    result = await db.execute(select(Deploy).where(Deploy.id == deploy_id))
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise HTTPException(status_code=404, detail="Deploy not found")

    # Ownership check for .own permissions
    project = await _get_project_for_deploy(db, deploy)
    _check_ownership(current_user, project, "deploys.rollback")

    # Must be in a state that can transition to rolled_back
    if not deploy.can_transition_to("rolled_back"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot rollback deploy in state '{deploy.status}'",
        )

    reason = body.reason if body and body.reason else "Manual rollback"

    # Find the previous successful deploy in the same environment
    # (one that was active and has an artifact we can redeploy)
    prev_result = await db.execute(
        select(Deploy)
        .where(
            Deploy.env_id == deploy.env_id,
            Deploy.id != deploy_id,
            Deploy.artifact_id.isnot(None),
            Deploy.status.in_(["active", "superseded", "stopped"]),
        )
        .order_by(Deploy.promoted_at.desc().nullslast(), Deploy.created_at.desc())
        .limit(1)
    )
    previous_deploy = prev_result.scalar_one_or_none()

    # Transition current deploy to rolled_back
    try:
        deploy = await transition_deploy(
            db,
            deploy_id=deploy_id,
            new_status="rolled_back",
            description=reason,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    if previous_deploy and previous_deploy.artifact_id:
        # Redeploy the previous artifact
        from app.models.build import Artifact, Build

        art_result = await db.execute(
            select(Artifact).where(Artifact.id == previous_deploy.artifact_id)
        )
        artifact = art_result.scalar_one_or_none()

        if artifact:
            build_result = await db.execute(
                select(Build).where(Build.id == artifact.build_id)
            )
            build = build_result.scalar_one_or_none()

            if build:
                env_result = await db.execute(
                    select(Environment).where(Environment.id == deploy.env_id)
                )
                environment = env_result.scalar_one_or_none()

                if environment:
                    try:
                        new_deploy = await trigger_deploy(
                            db,
                            project=project,
                            build=build,
                            artifact=artifact,
                            env_name=environment.name,
                            actor_user_id=current_user.id,
                        )

                        await write_audit_log(
                            db,
                            actor_user_id=current_user.id,
                            action="deploy.rollback.redeploy",
                            target_type="deploy",
                            target_id=str(deploy.id),
                            payload={
                                "reason": reason,
                                "previous_deploy_id": str(previous_deploy.id),
                                "new_deploy_id": str(new_deploy.id),
                            },
                        )
                        await db.commit()
                        return DeployResponse.model_validate(deploy)
                    except Exception as e:
                        # If redeployment fails, still complete the rollback
                        await write_audit_log(
                            db,
                            actor_user_id=current_user.id,
                            action="deploy.rollback.redeploy_failed",
                            target_type="deploy",
                            target_id=str(deploy.id),
                            payload={"reason": reason, "error": str(e)[:200]},
                        )

    # No previous deploy found (or redeploy failed) — full teardown
    from app.services.deploy_teardown import teardown_deploy
    await teardown_deploy(
        db,
        deploy_id,
        remove_production_route=True,  # no replacement, remove production URL
        destroy_container=True,
    )

    # Clear production URL on project since there's no active deploy
    project.production_url = None

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="deploy.rollback.teardown",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={"reason": reason, "action": "full_teardown"},
    )
    await db.commit()

    return DeployResponse.model_validate(deploy)


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
    _check_ownership(current_user, project, "deploys.destroy")

    # Already terminal?
    if deploy.status in ("rolled_back", "superseded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Deploy is already in terminal state '{deploy.status}'",
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
    Nginx routing is removed so traffic stops flowing.
    The deploy transitions from 'active' to 'stopped'.
    Can be restarted later with POST /deploys/{id}/start.
    """
    check_permission(current_user.role, "deploys.container")

    result = await db.execute(select(Deploy).where(Deploy.id == deploy_id))
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise HTTPException(status_code=404, detail="Deploy not found")

    project = await _get_project_for_deploy(db, deploy)
    _check_ownership(current_user, project, "deploys.container")

    if deploy.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Can only stop active deploys (current: '{deploy.status}')",
        )

    # Stop the LXC container (don't destroy it)
    from app.services.deploy_teardown import stop_lxc_container, _find_lxc_for_deploy
    from app.services.proxmox_adapter import get_proxmox_adapter
    from app.services.dns_routing import unregister_deploy_routing

    adapter = get_proxmox_adapter()

    env_result = await db.execute(select(Environment).where(Environment.id == deploy.env_id))
    environment = env_result.scalar_one_or_none()
    hostname = f"{project.slug}-{environment.name}" if environment else ""

    if hostname:
        lxc = await _find_lxc_for_deploy(adapter, hostname)
        if lxc:
            node, vmid = lxc
            await stop_lxc_container(adapter, node, vmid)

    # Remove Nginx routing (traffic should stop)
    await unregister_deploy_routing(str(deploy_id))

    # Transition to stopped
    deploy.status = "stopped"
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="deploy.stop",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={},
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
    _check_ownership(current_user, project, "deploys.container")

    if deploy.status != "stopped":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Can only start stopped deploys (current: '{deploy.status}')",
        )

    # Enforce container limit — may auto-stop other containers
    stopped_ids = await _enforce_container_limit(
        db, project.id, exclude_deploy_id=deploy_id,
    )

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
        payload={"auto_stopped": [str(sid) for sid in stopped_ids]},
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

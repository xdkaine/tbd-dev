"""Builds router - create, list, and manage build records.

M2 additions:
- Artifact intake endpoint (POST /projects/{id}/builds/{build_id}/artifacts)
- Build status transition endpoint (PATCH /projects/{id}/builds/{build_id})
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user, get_current_user_from_token
from app.models.build import Artifact, Build
from app.models.deploy import Deploy
from app.models.environment import Environment
from app.models.project import Project, Repo
from app.schemas.build import BuildCreate, BuildListResponse, BuildLogsResponse, BuildResponse
from app.services.audit import write_audit_log
from app.services.build_coordinator import ContainerLimitError, create_build_for_push, intake_artifact, trigger_deploy
from app.services.deploy_executor import DeployContext, execute_deploy
from app.services.github import get_branch_head_sha, get_owner_github_token
from app.services.rbac import Role, check_permission
from app.utils.project_access import is_project_contributor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/builds", tags=["builds"])


# ---------------------------------------------------------------------------
# Schemas for M2 endpoints
# ---------------------------------------------------------------------------


class ArtifactIntakeRequest(BaseModel):
    """Request body when Actions runner reports a built artifact."""

    image_ref: str = Field(..., description="Full OCI image reference (e.g. registry.sdc.cpp/tbd/app:sha)")
    sha256: str = Field(..., description="Image digest (sha256:...)")
    size: int = Field(0, ge=0, description="Image size in bytes")


class ArtifactResponse(BaseModel):
    """Artifact in API responses."""

    id: uuid.UUID
    build_id: uuid.UUID
    image_ref: str
    sha256: str
    size: int
    stored_at: datetime | None

    model_config = {"from_attributes": True}


class BuildUpdateRequest(BaseModel):
    """Request to update build status (used by Actions runner)."""

    status: str = Field(..., description="New build status")
    image_ref: str | None = None


class DeployTriggerRequest(BaseModel):
    """Request to trigger a deploy from a build artifact."""

    env: str = Field(..., description="Target environment name (e.g. 'production', 'pr-42')")


class DeployTriggerResponse(BaseModel):
    """Response after triggering a deploy."""

    deploy_id: uuid.UUID
    build_id: uuid.UUID
    artifact_id: uuid.UUID
    env: str
    status: str
    url: str | None


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=BuildListResponse)
async def list_builds(
    project_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List builds for a project."""
    check_permission(current_user.role, "builds.read")

    # Verify project access
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        if not await is_project_contributor(db, project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Project not found")

    query = select(Build).where(Build.project_id == project_id)
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(Build.started_at.desc().nullslast())
    )
    builds = result.scalars().all()

    return BuildListResponse(
        items=[BuildResponse.model_validate(b) for b in builds],
        total=total,
    )


@router.get("/{build_id}", response_model=BuildResponse)
async def get_build(
    project_id: uuid.UUID,
    build_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single build by ID."""
    check_permission(current_user.role, "builds.read")

    result = await db.execute(
        select(Build).where(Build.id == build_id, Build.project_id == project_id)
    )
    build = result.scalar_one_or_none()
    if build is None:
        raise HTTPException(status_code=404, detail="Build not found")

    return BuildResponse.model_validate(build)


@router.get("/{build_id}/logs", response_model=BuildLogsResponse)
async def get_build_logs(
    project_id: uuid.UUID,
    build_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get build logs for a specific build.

    Returns the build status and log output from the build pipeline.
    Logs are only available for builds executed by the built-in builder.
    """
    check_permission(current_user.role, "builds.read")

    result = await db.execute(
        select(Build).where(Build.id == build_id, Build.project_id == project_id)
    )
    build = result.scalar_one_or_none()
    if build is None:
        raise HTTPException(status_code=404, detail="Build not found")

    return BuildLogsResponse(
        build_id=build.id,
        status=build.status,
        logs=build.logs,
    )


TERMINAL_BUILD_STATUSES = frozenset(["success", "failed", "cancelled"])


@router.get("/{build_id}/logs/stream")
async def stream_build_logs(
    project_id: uuid.UUID,
    build_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Stream build logs via Server-Sent Events.

    Polls the database every 500ms and sends new log content as SSE events.
    Automatically closes when the build reaches a terminal state.

    Event types:
    - `log`: partial log payload with `logs` (full text) and `status`
    - `done`: final event when the build has finished
    """
    check_permission(current_user.role, "builds.read")

    result = await db.execute(
        select(Build).where(Build.id == build_id, Build.project_id == project_id)
    )
    build = result.scalar_one_or_none()
    if build is None:
        raise HTTPException(status_code=404, detail="Build not found")

    async def event_generator():
        """Yield SSE events as the build progresses."""
        import json
        import time

        from app.config import settings

        last_len = 0
        last_heartbeat = time.monotonic()
        started_at = time.monotonic()
        max_duration = settings.sse_stream_timeout_seconds

        while True:
            await db.refresh(build)

            current_logs = build.logs or ""
            current_status = build.status

            if len(current_logs) > last_len:
                data = json.dumps({
                    "logs": current_logs,
                    "status": current_status,
                })
                yield f"event: log\ndata: {data}\n\n"
                last_len = len(current_logs)
                last_heartbeat = time.monotonic()

            if current_status in TERMINAL_BUILD_STATUSES:
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


@router.post("", response_model=BuildResponse, status_code=status.HTTP_201_CREATED)
async def create_build(
    project_id: uuid.UUID,
    body: BuildCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new build record (typically called by GitHub Actions)."""
    check_permission(current_user.role, "builds.create")

    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    build = Build(
        project_id=project_id,
        commit_sha=body.commit_sha,
        image_ref=body.image_ref,
        status="building",
        started_at=datetime.now(timezone.utc),
    )
    db.add(build)
    await db.flush()

    # Audit
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="build.create",
        target_type="build",
        target_id=str(build.id),
        payload={"project_id": str(project_id), "commit_sha": body.commit_sha},
    )

    return BuildResponse.model_validate(build)


# ---------------------------------------------------------------------------
# Manual rebuild trigger
# ---------------------------------------------------------------------------


@router.post("/trigger", response_model=BuildResponse, status_code=status.HTTP_201_CREATED)
async def trigger_rebuild(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a manual rebuild from the HEAD of the default branch.

    Fetches the latest commit SHA from GitHub, creates a build record,
    and launches the build pipeline. This lets users re-trigger builds
    from the UI without needing to push a new commit.
    """
    check_permission(current_user.role, "builds.create")

    # Verify project exists and user has access
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        if not await is_project_contributor(db, project_id, current_user.id):
            raise HTTPException(status_code=404, detail="Project not found")

    # Get linked repo
    repo_result = await db.execute(
        select(Repo).where(Repo.project_id == project_id)
    )
    repo = repo_result.scalar_one_or_none()
    if repo is None or not repo.repo_full_name:
        raise HTTPException(
            status_code=400,
            detail="No GitHub repository connected. Connect a repo first.",
        )

    # Get the owner's OAuth token
    owner_token = await get_owner_github_token(db, project.id)
    if not owner_token:
        raise HTTPException(
            status_code=400,
            detail="No GitHub OAuth token found. Reconnect your GitHub account.",
        )

    # Fetch HEAD commit SHA of the default branch
    head_sha = await get_branch_head_sha(
        token=owner_token,
        repo_full_name=repo.repo_full_name,
        branch=repo.default_branch,
    )
    if not head_sha:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch HEAD of {repo.default_branch} from GitHub.",
        )

    # Create a build record
    build = await create_build_for_push(
        db,
        repo=repo,
        commit_sha=head_sha,
        ref=f"refs/heads/{repo.default_branch}",
    )
    build.trigger = "manual"
    await db.commit()

    # Launch the builder in the background (concurrency + timeout guarded)
    from app.services.builder import launch_build
    await launch_build(build.id)

    # Refresh so the response reflects committed state
    await db.refresh(build)

    return BuildResponse.model_validate(build)


# ---------------------------------------------------------------------------
# M2: Artifact intake
# ---------------------------------------------------------------------------


@router.post(
    "/{build_id}/artifacts",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_artifact(
    project_id: uuid.UUID,
    build_id: uuid.UUID,
    body: ArtifactIntakeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record an artifact after GitHub Actions pushes an OCI image.

    This endpoint is called by the Actions runner after `docker push`
    completes. It marks the build as successful and records the artifact
    metadata (image ref, digest, size).
    """
    check_permission(current_user.role, "builds.create")

    # Verify build exists and belongs to project
    build_result = await db.execute(
        select(Build).where(Build.id == build_id, Build.project_id == project_id)
    )
    build = build_result.scalar_one_or_none()
    if build is None:
        raise HTTPException(status_code=404, detail="Build not found")

    try:
        artifact = await intake_artifact(
            db,
            build_id=build_id,
            image_ref=body.image_ref,
            image_sha256=body.sha256,
            image_size=body.size,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ArtifactResponse.model_validate(artifact)


# ---------------------------------------------------------------------------
# M2: Deploy trigger from build
# ---------------------------------------------------------------------------


async def _run_deploy_executor(
    deploy_id: uuid.UUID,
    artifact_id: uuid.UUID,
    build_id: uuid.UUID,
    project_id: uuid.UUID,
    env_id: uuid.UUID,
) -> None:
    """Background task to execute the deploy pipeline.

    Creates its own database session to avoid sharing with the request.
    """
    from app.database import async_session_factory

    try:
        async with async_session_factory() as db:
            # Reload all records from fresh session
            deploy = (await db.execute(select(Deploy).where(Deploy.id == deploy_id))).scalar_one()
            artifact = (await db.execute(select(Artifact).where(Artifact.id == artifact_id))).scalar_one()
            build = (await db.execute(select(Build).where(Build.id == build_id))).scalar_one()
            project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
            environment = (await db.execute(select(Environment).where(Environment.id == env_id))).scalar_one()

            ctx = DeployContext(
                deploy=deploy,
                artifact=artifact,
                build=build,
                project=project,
                environment=environment,
            )

            await execute_deploy(db, ctx)
            await db.commit()
    except Exception as e:
        logger.exception("Background deploy executor failed for deploy %s: %s", deploy_id, e)


@router.post(
    "/{build_id}/deploy",
    response_model=DeployTriggerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def deploy_from_build(
    project_id: uuid.UUID,
    build_id: uuid.UUID,
    body: DeployTriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a deploy from a completed build.

    This is the main entry point for GitHub Actions to trigger a deployment
    after the image has been pushed and the artifact recorded. The Actions
    workflow calls:
      1. POST /projects/{id}/builds/{build_id}/artifacts  (record the image)
      2. POST /projects/{id}/builds/{build_id}/deploy     (trigger deploy)
    """
    check_permission(current_user.role, "deploys.create")

    # Verify project
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify build
    build_result = await db.execute(
        select(Build).where(Build.id == build_id, Build.project_id == project_id)
    )
    build = build_result.scalar_one_or_none()
    if build is None:
        raise HTTPException(status_code=404, detail="Build not found")

    # Verify artifact exists
    if build.artifact is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Build has no artifact. Record the artifact first via POST .../artifacts",
        )

    try:
        deploy = await trigger_deploy(
            db,
            project=project,
            build=build,
            artifact=build.artifact,
            env_name=body.env,
            actor_user_id=current_user.id,
        )
    except ContainerLimitError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Resolve the environment for the background task
    env_result = await db.execute(
        select(Environment).where(Environment.id == deploy.env_id)
    )
    environment = env_result.scalar_one()

    # Schedule the deploy executor as a background task
    background_tasks.add_task(
        _run_deploy_executor,
        deploy_id=deploy.id,
        artifact_id=build.artifact.id,
        build_id=build.id,
        project_id=project.id,
        env_id=environment.id,
    )

    return DeployTriggerResponse(
        deploy_id=deploy.id,
        build_id=build.id,
        artifact_id=build.artifact.id,
        env=body.env,
        status=deploy.status,
        url=deploy.url,
    )

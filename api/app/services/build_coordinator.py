"""Build coordinator service.

Orchestrates the build-to-deploy pipeline:
1. Creates build records when webhooks arrive
2. Accepts artifact intake from GitHub Actions (image_ref + sha)
3. Transitions build states and creates deploy records
4. Reports status back to GitHub via the github service
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.build import Artifact, Build
from app.models.deploy import Deploy
from app.models.environment import Environment
from app.models.project import Project, Repo
from app.services.audit import write_audit_log
from app.services.deploy_queue import enqueue_deploy, mark_superseded, on_deploy_completed
from app.services.github import get_owner_github_token, post_commit_status_oauth
from app.services.quota_enforcement import QuotaExceededError, check_user_aggregate_quota
from app.utils.dns import deploy_url

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Build lifecycle
# ---------------------------------------------------------------------------


async def create_build_for_push(
    db: AsyncSession,
    repo: Repo,
    commit_sha: str,
    ref: str,
) -> Build:
    """Create a build record when a push webhook is received.

    Also posts a 'pending' commit status to GitHub.
    """
    # Extract branch name from ref (e.g. "refs/heads/main" -> "main")
    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref

    build = Build(
        project_id=repo.project_id,
        commit_sha=commit_sha,
        status="queued",
        trigger="push",
        branch=branch,
    )
    db.add(build)
    await db.flush()

    logger.info(
        "Created build %s for project %s (sha=%s, ref=%s)",
        build.id,
        repo.project_id,
        commit_sha[:8],
        ref,
    )

    # Post pending status to GitHub
    if repo.repo_full_name:
        owner_token = await get_owner_github_token(db, repo.project_id)
        if owner_token:
            await post_commit_status_oauth(
                token=owner_token,
                repo_full_name=repo.repo_full_name,
                commit_sha=commit_sha,
                state="queued",
                description="Build queued",
            )

    await write_audit_log(
        db,
        actor_user_id=None,
        action="build.create",
        target_type="build",
        target_id=str(build.id),
        payload={
            "project_id": str(repo.project_id),
            "commit_sha": commit_sha,
            "ref": ref,
            "trigger": "webhook",
        },
    )

    return build


async def create_build_for_pr(
    db: AsyncSession,
    repo: Repo,
    commit_sha: str,
    pr_number: int,
) -> Build:
    """Create a build record when a pull request webhook is received."""
    build = Build(
        project_id=repo.project_id,
        commit_sha=commit_sha,
        status="queued",
        trigger="pull_request",
        branch=f"pr-{pr_number}",
    )
    db.add(build)
    await db.flush()

    logger.info(
        "Created build %s for project %s PR #%d (sha=%s)",
        build.id,
        repo.project_id,
        pr_number,
        commit_sha[:8],
    )

    # Post pending status to GitHub
    if repo.repo_full_name:
        owner_token = await get_owner_github_token(db, repo.project_id)
        if owner_token:
            await post_commit_status_oauth(
                token=owner_token,
                repo_full_name=repo.repo_full_name,
                commit_sha=commit_sha,
                state="queued",
                description=f"Build queued for PR #{pr_number}",
            )

    await write_audit_log(
        db,
        actor_user_id=None,
        action="build.create",
        target_type="build",
        target_id=str(build.id),
        payload={
            "project_id": str(repo.project_id),
            "commit_sha": commit_sha,
            "pr_number": pr_number,
            "trigger": "pull_request",
        },
    )

    return build


# ---------------------------------------------------------------------------
# Artifact intake (called by Actions runner after image push)
# ---------------------------------------------------------------------------


async def intake_artifact(
    db: AsyncSession,
    build_id: uuid.UUID,
    image_ref: str,
    image_sha256: str,
    image_size: int = 0,
) -> Artifact:
    """Record an artifact after GitHub Actions pushes an OCI image to the registry.

    Transitions the build from building -> artifact_ready (or queued -> building -> artifact_ready).
    """
    result = await db.execute(
        select(Build)
        .where(Build.id == build_id)
        .options()
    )
    build = result.scalar_one_or_none()
    if build is None:
        raise ValueError(f"Build {build_id} not found")

    # Update build with image reference
    build.image_ref = image_ref
    build.status = "success"
    build.finished_at = datetime.now(timezone.utc)

    # Create artifact record
    artifact = Artifact(
        build_id=build_id,
        image_ref=image_ref,
        sha256=image_sha256,
        size=image_size,
        stored_at=datetime.now(timezone.utc),
    )
    db.add(artifact)
    await db.flush()

    logger.info(
        "Artifact created for build %s: image=%s sha256=%s",
        build_id,
        image_ref,
        image_sha256[:16],
    )

    # Report status to GitHub
    repo = await _get_repo_for_build(db, build)
    if repo and repo.repo_full_name:
        owner_token = await get_owner_github_token(db, build.project_id)
        if owner_token:
            await post_commit_status_oauth(
                token=owner_token,
                repo_full_name=repo.repo_full_name,
                commit_sha=build.commit_sha,
                state="artifact_ready",
                description="Artifact ready, deploy starting",
            )

    await write_audit_log(
        db,
        actor_user_id=None,
        action="artifact.create",
        target_type="artifact",
        target_id=str(artifact.id),
        payload={
            "build_id": str(build_id),
            "image_ref": image_ref,
            "sha256": image_sha256,
            "size": image_size,
        },
    )

    return artifact


# ---------------------------------------------------------------------------
# Deploy triggering
# ---------------------------------------------------------------------------


async def trigger_deploy(
    db: AsyncSession,
    project: Project,
    build: Build,
    artifact: Artifact,
    env_name: str,
    actor_user_id: uuid.UUID | None = None,
) -> Deploy:
    """Create and enqueue a deploy for a build artifact.

    Resolves the target environment (auto-creates preview envs for PRs),
    generates the deploy URL, enqueues through the deploy queue, and
    reports status to GitHub.
    """
    # Check deploy lock (deploy freeze)
    if project.deploy_locked:
        raise ValueError(
            f"Deploys are currently locked for project '{project.slug}'. "
            "A staff member must unlock deploys before new deployments can proceed."
        )

    # Check aggregate user quota (total resources across all projects)
    try:
        await check_user_aggregate_quota(db, project.owner_id)
    except QuotaExceededError as e:
        logger.warning(
            "Aggregate quota exceeded for user %s on project %s: %s",
            project.owner_id, project.slug, e,
        )
        raise ValueError(str(e)) from e

    # Resolve environment
    env_result = await db.execute(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.name == env_name,
        )
    )
    environment = env_result.scalar_one_or_none()

    # Auto-create preview environments for PRs
    if environment is None and env_name.startswith("pr-"):
        environment = Environment(
            project_id=project.id,
            name=env_name,
            type="preview",
        )
        db.add(environment)
        await db.flush()
        logger.info("Auto-created preview env '%s' for project %s", env_name, project.slug)
    elif environment is None:
        raise ValueError(f"Environment '{env_name}' not found for project {project.slug}")

    # Generate URL: <deployid>-<username>.dev.sdc.cpp
    # We need a deploy ID first, so create the deploy, then set the URL
    deploy = Deploy(
        env_id=environment.id,
        artifact_id=artifact.id,
        status="queued",
    )
    db.add(deploy)
    await db.flush()  # Assigns deploy.id

    # Resolve owner username for the URL
    owner_username = project.owner.username if project.owner else "unknown"
    url = deploy_url(deploy.id, owner_username)
    deploy.url = url

    # Enqueue with concurrency control
    deploy = await enqueue_deploy(db, deploy)

    # Report status to GitHub
    repo = await _get_repo_for_build(db, build)
    if repo and repo.repo_full_name:
        owner_token = await get_owner_github_token(db, project.id)
        if owner_token:
            await post_commit_status_oauth(
                token=owner_token,
                repo_full_name=repo.repo_full_name,
                commit_sha=build.commit_sha,
                state=deploy.status,
                description=f"Deploy {deploy.status}",
                target_url=url,
            )

    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="deploy.create",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={
            "project_id": str(project.id),
            "build_id": str(build.id),
            "artifact_id": str(artifact.id),
            "env": env_name,
            "url": url,
        },
    )

    logger.info(
        "Deploy %s created for project %s env %s (status=%s)",
        deploy.id,
        project.slug,
        env_name,
        deploy.status,
    )

    return deploy


# ---------------------------------------------------------------------------
# State transition helpers (called by runtime plane in M3)
# ---------------------------------------------------------------------------


async def transition_deploy(
    db: AsyncSession,
    deploy_id: uuid.UUID,
    new_status: str,
    description: str = "",
) -> Deploy:
    """Transition a deploy to a new state.

    Validates the transition against the state machine, updates the record,
    reports to GitHub, and handles side effects (e.g., marking superseded deploys).

    When transitioning to 'active', locks the row with FOR UPDATE and
    checks whether a *newer* deploy already reached 'active' for this
    environment.  If so, this deploy is marked 'superseded' instead to
    prevent an older deploy from stealing the production URL.
    """
    # Lock the deploy row to serialise concurrent transitions for the
    # same deploy (prevents two callers from reading the same old status).
    result = await db.execute(
        select(Deploy).where(Deploy.id == deploy_id).with_for_update()
    )
    deploy = result.scalar_one_or_none()
    if deploy is None:
        raise ValueError(f"Deploy {deploy_id} not found")

    if not deploy.can_transition_to(new_status):
        raise ValueError(
            f"Invalid transition: {deploy.status} -> {new_status} "
            f"(allowed: {', '.join(deploy._valid_transitions())})"
            if hasattr(deploy, '_valid_transitions')
            else f"Invalid transition: {deploy.status} -> {new_status}"
        )

    # --- Newest-deploy guard ---
    # If we are about to promote to 'active', verify no newer deploy
    # has already been promoted in this environment.  This handles the
    # race where two deploys pass health checks near-simultaneously.
    if new_status == "active":
        newer_active = await db.execute(
            select(Deploy).where(
                Deploy.env_id == deploy.env_id,
                Deploy.status == "active",
                Deploy.promoted_at.isnot(None),
                Deploy.created_at > deploy.created_at,
            ).limit(1)
        )
        if newer_active.scalar_one_or_none() is not None:
            logger.warning(
                "Deploy %s lost promotion race — a newer deploy is already active; "
                "marking as superseded instead of active",
                deploy_id,
            )
            new_status = "superseded"
            description = "Superseded by a newer deploy that promoted first"

    old_status = deploy.status
    deploy.status = new_status

    # Side effects
    if new_status == "active":
        deploy.promoted_at = datetime.now(timezone.utc)
        # Mark previous active deploys as superseded
        superseded_ids = await mark_superseded(db, deploy.env_id, deploy.id)

        # Trigger teardown for each superseded deploy (destroy container +
        # remove per-deploy Nginx config).  mark_superseded() bypasses
        # transition_deploy() to avoid recursion, so the teardown hook
        # in the "superseded" branch below wouldn't fire for those deploys.
        if superseded_ids:
            from app.services.deploy_teardown import teardown_deploy
            for sid in superseded_ids:
                try:
                    await teardown_deploy(
                        db, sid,
                        remove_production_route=False,
                        destroy_container=True,
                    )
                except Exception as e:
                    logger.warning(
                        "Non-fatal: teardown for superseded deploy %s failed: %s",
                        sid, e,
                    )

    if new_status in ("active", "failed", "rolled_back", "superseded", "stopped"):
        # Terminal or stable state — free a queue slot
        await on_deploy_completed(db, deploy.env_id)

    # Infrastructure cleanup for terminal states that deactivate a deploy.
    # When a deploy is superseded or rolled back, tear down its Nginx config
    # and LXC container so resources are freed. This runs async fire-and-forget
    # so it doesn't block the state transition.
    if new_status in ("superseded", "rolled_back"):
        try:
            from app.services.deploy_teardown import teardown_deploy
            await teardown_deploy(
                db,
                deploy_id,
                remove_production_route=False,  # production route points to the new active deploy
                destroy_container=True,
            )
        except Exception as e:
            logger.warning(
                "Non-fatal: teardown failed for deploy %s during %s transition: %s",
                deploy_id, new_status, e,
            )

    await db.flush()

    # Report to GitHub
    build = await _get_build_for_deploy(db, deploy)
    if build:
        repo = await _get_repo_for_build(db, build)
        if repo and repo.repo_full_name:
            owner_token = await get_owner_github_token(db, build.project_id)
            if owner_token:
                await post_commit_status_oauth(
                    token=owner_token,
                    repo_full_name=repo.repo_full_name,
                    commit_sha=build.commit_sha,
                    state=new_status,
                    description=description or f"Deploy {new_status}",
                    target_url=deploy.url,
                )

    await write_audit_log(
        db,
        actor_user_id=None,
        action="deploy.transition",
        target_type="deploy",
        target_id=str(deploy.id),
        payload={
            "from": old_status,
            "to": new_status,
            "description": description,
        },
    )

    logger.info("Deploy %s transitioned: %s -> %s", deploy_id, old_status, new_status)
    return deploy


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_repo_for_build(db: AsyncSession, build: Build) -> Repo | None:
    """Look up the repo linked to a build's project."""
    result = await db.execute(
        select(Repo).where(Repo.project_id == build.project_id)
    )
    return result.scalar_one_or_none()


async def _get_build_for_deploy(db: AsyncSession, deploy: Deploy) -> Build | None:
    """Look up the build associated with a deploy's artifact."""
    if deploy.artifact_id is None:
        return None
    result = await db.execute(
        select(Build)
        .join(Artifact, Artifact.build_id == Build.id)
        .where(Artifact.id == deploy.artifact_id)
    )
    return result.scalar_one_or_none()

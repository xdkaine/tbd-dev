"""GitHub integration router - webhook receiver, app install, repo browsing.

Endpoints:
- POST /integrations/github/install        — link a GitHub App installation
- POST /integrations/github/webhook        — receive GitHub webhook events
- GET  /integrations/github/repos          — list repos from all installations
- POST /projects/{id}/repo                 — connect a GitHub repo to a project
- DELETE /projects/{id}/repo               — disconnect a repo from a project
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.project import Project, Repo
from app.schemas.project import RepoResponse
from app.services.audit import write_audit_log
from app.services.build_coordinator import create_build_for_pr, create_build_for_push
from app.services.github import (
    create_repo_webhook,
    get_branch_head_sha,
    list_installation_repos,
    list_installations,
    verify_webhook_signature,
)
from app.services.rbac import check_permission
from app.utils.project_access import is_project_contributor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/github", tags=["github"])

# Secondary router for project-scoped repo endpoints (mounted separately)
repo_router = APIRouter(prefix="/projects/{project_id}", tags=["github"])


# ---------------------------------------------------------------------------
# GitHub App installation
# ---------------------------------------------------------------------------


@router.post("/install")
async def install_github_app(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a GitHub App installation for a project.

    Called after a user installs the TBD GitHub App on their repository.
    Links the GitHub repo to a TBD project.
    """
    check_permission(current_user.role, "projects.update")

    body = await request.json()
    project_id = body.get("project_id")
    repo_id = body.get("repo_id")
    install_id = body.get("install_id")
    repo_full_name = body.get("repo_full_name")  # e.g. "owner/repo"
    default_branch = body.get("default_branch", "main")

    if not all([project_id, repo_id, install_id]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id, repo_id, and install_id are required",
        )

    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create or update repo link
    repo_result = await db.execute(select(Repo).where(Repo.project_id == project_id))
    repo = repo_result.scalar_one_or_none()

    if repo:
        repo.repo_id = str(repo_id)
        repo.repo_full_name = repo_full_name
        repo.default_branch = default_branch or "main"
        repo.install_id = str(install_id)
    else:
        repo = Repo(
            project_id=project_id,
            provider="github",
            repo_id=str(repo_id),
            repo_full_name=repo_full_name,
            default_branch=default_branch or "main",
            install_id=str(install_id),
        )
        db.add(repo)

    await db.flush()

    # Audit
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="github.install",
        target_type="repo",
        target_id=str(repo.id),
        payload={
            "project_id": str(project_id),
            "repo_id": str(repo_id),
            "repo_full_name": repo_full_name,
            "install_id": str(install_id),
        },
    )

    return {
        "status": "ok",
        "repo_id": str(repo.id),
        "repo_full_name": repo_full_name,
    }


# ---------------------------------------------------------------------------
# List available repos from GitHub App installations
# ---------------------------------------------------------------------------


class GitHubRepoItem(BaseModel):
    """A repository available from a GitHub App installation."""

    id: int
    full_name: str
    name: str
    private: bool
    default_branch: str
    description: str | None = None
    html_url: str
    install_id: int


@router.get("/repos", response_model=list[GitHubRepoItem])
async def list_github_repos(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all repositories accessible to the TBD GitHub App.

    Fetches repos from every installation of the GitHub App and returns
    them in a flat list. Each item includes the install_id so the frontend
    can pass it when connecting a repo to a project.
    """
    check_permission(current_user.role, "projects.create")

    try:
        installations = await list_installations()
    except Exception:
        logger.exception("Failed to list GitHub App installations")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to communicate with GitHub",
        )

    all_repos: list[GitHubRepoItem] = []
    for inst in installations:
        install_id = inst.get("id")
        if not install_id:
            continue
        try:
            repos = await list_installation_repos(str(install_id))
            for r in repos:
                all_repos.append(
                    GitHubRepoItem(
                        id=r["id"],
                        full_name=r["full_name"],
                        name=r["name"],
                        private=r.get("private", False),
                        default_branch=r.get("default_branch", "main"),
                        description=r.get("description"),
                        html_url=r.get("html_url", ""),
                        install_id=install_id,
                    )
                )
        except Exception:
            logger.warning(
                "Failed to list repos for installation %s, skipping", install_id
            )

    return all_repos


# ---------------------------------------------------------------------------
# Connect / disconnect a repo to a project
# ---------------------------------------------------------------------------


class ConnectRepoRequest(BaseModel):
    """Request body to connect a GitHub repo to a project."""

    install_id: int | None = Field(None, description="GitHub App installation ID (optional, legacy)")
    repo_id: int = Field(..., description="GitHub repository numeric ID")
    repo_full_name: str = Field(..., description="owner/repo")
    default_branch: str = Field("main", description="Default branch name")


@repo_router.post("/repo", response_model=RepoResponse, status_code=status.HTTP_201_CREATED)
async def connect_repo(
    project_id: uuid.UUID,
    body: ConnectRepoRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Connect a GitHub repository to a project.

    Creates (or updates) the Repo record linking the project to a GitHub repo.
    If the project already has a repo, it is replaced.
    """
    check_permission(current_user.role, "projects.update")

    # Verify project exists and user has access
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.rbac import Role
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        if not await is_project_contributor(db, project_id, current_user.id):
            raise HTTPException(status_code=403, detail="Cannot modify another user's project")

    # Create or update
    repo_result = await db.execute(select(Repo).where(Repo.project_id == project_id))
    repo = repo_result.scalar_one_or_none()

    install_id_str = str(body.install_id) if body.install_id else None

    if repo:
        repo.repo_id = str(body.repo_id)
        repo.repo_full_name = body.repo_full_name
        repo.default_branch = body.default_branch
        repo.install_id = install_id_str
    else:
        repo = Repo(
            project_id=project_id,
            provider="github",
            repo_id=str(body.repo_id),
            repo_full_name=body.repo_full_name,
            default_branch=body.default_branch,
            install_id=install_id_str,
        )
        db.add(repo)

    await db.flush()

    # Create a webhook on the repo using the owner's OAuth token.
    # The webhook sends push/PR events to the Smee relay which forwards
    # to our internal webhook receiver.
    from app.models.user import User

    user_result = await db.execute(select(User).where(User.id == current_user.id))
    user = user_result.scalar_one_or_none()

    if user and user.github_token:
        from app.config import settings as app_settings

        webhook_url = "https://smee.io/5yCWAJS2wt6g3Eip"
        webhook_secret = app_settings.github_webhook_secret or None
        hook = await create_repo_webhook(
            token=user.github_token,
            repo_full_name=body.repo_full_name,
            webhook_url=webhook_url,
            secret=webhook_secret,
        )
        if hook:
            logger.info("Webhook set up for %s", body.repo_full_name)
        else:
            logger.warning("Failed to create webhook for %s", body.repo_full_name)
    else:
        logger.warning(
            "No GitHub token for user %s — webhook not created for %s",
            current_user.username,
            body.repo_full_name,
        )

    # --- Trigger initial build (like Vercel: import = immediate build) ---
    # Fetch the HEAD commit of the default branch and kick off a build.
    initial_build_id = None
    if user and user.github_token:
        head_sha = await get_branch_head_sha(
            token=user.github_token,
            repo_full_name=body.repo_full_name,
            branch=body.default_branch,
        )
        if head_sha:
            ref = f"refs/heads/{body.default_branch}"
            build = await create_build_for_push(db, repo, head_sha, ref)
            initial_build_id = build.id
            logger.info(
                "Initial build %s created for %s @ %s",
                build.id,
                body.repo_full_name,
                head_sha[:8],
            )
        else:
            logger.warning(
                "Could not fetch HEAD SHA for %s/%s — skipping initial build",
                body.repo_full_name,
                body.default_branch,
            )

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="repo.connect",
        target_type="repo",
        target_id=str(repo.id),
        payload={
            "project_id": str(project_id),
            "repo_full_name": body.repo_full_name,
            "install_id": body.install_id,
        },
    )

    # Commit so the background builder can see the build record
    await db.commit()

    # Launch the builder as a background task (after commit, same as webhook handler)
    if initial_build_id:
        from app.services.builder import launch_build
        await launch_build(initial_build_id)
        logger.info("Builder launched for initial build %s", initial_build_id)

    # Refresh repo after commit (attributes may be expired)
    await db.refresh(repo)
    return RepoResponse.model_validate(repo)


@repo_router.delete("/repo", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_repo(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a GitHub repository from a project.

    Deletes the Repo record. Does not delete builds or deploys already created.
    """
    check_permission(current_user.role, "projects.update")

    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.rbac import Role
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        if not await is_project_contributor(db, project_id, current_user.id):
            raise HTTPException(status_code=403, detail="Cannot modify another user's project")

    repo_result = await db.execute(select(Repo).where(Repo.project_id == project_id))
    repo = repo_result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail="No repo connected to this project")

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="repo.disconnect",
        target_type="repo",
        target_id=str(repo.id),
        payload={
            "project_id": str(project_id),
            "repo_full_name": repo.repo_full_name,
        },
    )

    await db.delete(repo)
    await db.flush()


# ---------------------------------------------------------------------------
# Webhook receiver
# ---------------------------------------------------------------------------


@router.post("/webhook")
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_github_event: str = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    x_github_delivery: str = Header(None, alias="X-GitHub-Delivery"),
):
    """Receive GitHub webhook events.

    Handles:
    - push: triggers production build for default branch pushes
    - pull_request (opened/synchronize): triggers preview build
    - pull_request (closed): cleans up preview environment
    - ping: health check response

    All payloads are verified against the webhook signing secret.
    """
    body = await request.body()

    # Verify webhook signature
    if not verify_webhook_signature(body, x_hub_signature_256):
        logger.warning(
            "Webhook signature verification failed (delivery=%s)", x_github_delivery
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    payload = await request.json()
    event_type = x_github_event

    logger.info(
        "GitHub webhook received: event=%s delivery=%s",
        event_type,
        x_github_delivery,
    )

    if event_type == "push":
        return await _handle_push(payload, db)
    elif event_type == "pull_request":
        return await _handle_pull_request(payload, db)
    elif event_type == "ping":
        return {"status": "pong"}
    else:
        logger.info("Ignoring GitHub event: %s", event_type)
        return {"status": "ignored", "event": event_type}


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


async def _handle_push(payload: dict, db: AsyncSession) -> dict:
    """Handle a push event.

    Only triggers a build if the push is to the repo's default branch
    (production deploys). Non-default branch pushes are ignored.
    """
    repo_id = str(payload.get("repository", {}).get("id", ""))
    ref = payload.get("ref", "")  # e.g. "refs/heads/main"
    commit_sha = payload.get("after", "")
    repo_full_name = payload.get("repository", {}).get("full_name", "")

    logger.info("GitHub push: repo=%s ref=%s sha=%s", repo_full_name, ref, commit_sha)

    # Find linked project
    repo_result = await db.execute(select(Repo).where(Repo.repo_id == repo_id))
    repo = repo_result.scalar_one_or_none()

    if repo is None:
        logger.warning("No project linked to GitHub repo %s (%s)", repo_id, repo_full_name)
        return {"status": "no_project"}

    # Update repo_full_name if not set (backfill from webhook data)
    if not repo.repo_full_name and repo_full_name:
        repo.repo_full_name = repo_full_name
        await db.flush()

    # Only build on default branch pushes
    default_ref = f"refs/heads/{repo.default_branch}"
    if ref != default_ref:
        logger.info(
            "Ignoring push to non-default branch: %s (default: %s)", ref, default_ref
        )
        return {"status": "ignored", "reason": "non-default branch"}

    # Ignore zero SHAs (branch deletion)
    if commit_sha == "0" * 40:
        return {"status": "ignored", "reason": "branch deleted"}

    # Create build record via build coordinator
    build = await create_build_for_push(db, repo, commit_sha, ref)

    # Audit the webhook
    await write_audit_log(
        db,
        actor_user_id=None,
        action="github.push",
        target_type="project",
        target_id=str(repo.project_id),
        payload={
            "repo_id": repo_id,
            "ref": ref,
            "commit_sha": commit_sha,
            "build_id": str(build.id),
        },
    )

    # Commit the build record so the background builder can see it
    await db.commit()

    # Launch the built-in builder as a background task
    from app.services.builder import launch_build
    await launch_build(build.id)
    logger.info("Builder launched for build %s", build.id)

    return {
        "status": "build_created",
        "project_id": str(repo.project_id),
        "build_id": str(build.id),
        "commit_sha": commit_sha,
    }


async def _handle_pull_request(payload: dict, db: AsyncSession) -> dict:
    """Handle a pull_request event.

    - opened / synchronize: creates a preview build
    - closed: marks preview environment for cleanup
    """
    action = payload.get("action", "")
    pr_number = payload.get("number")
    repo_id = str(payload.get("repository", {}).get("id", ""))
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    head_sha = payload.get("pull_request", {}).get("head", {}).get("sha", "")

    logger.info(
        "GitHub PR: repo=%s action=%s pr=#%s sha=%s",
        repo_full_name,
        action,
        pr_number,
        head_sha[:8] if head_sha else "?",
    )

    # Find linked project
    repo_result = await db.execute(select(Repo).where(Repo.repo_id == repo_id))
    repo = repo_result.scalar_one_or_none()

    if repo is None:
        return {"status": "no_project"}

    # Update repo_full_name if not set
    if not repo.repo_full_name and repo_full_name:
        repo.repo_full_name = repo_full_name
        await db.flush()

    # Only build on opened and synchronize (new commits pushed to PR)
    if action in ("opened", "synchronize", "reopened"):
        build = await create_build_for_pr(db, repo, head_sha, int(pr_number or 0))

        await write_audit_log(
            db,
            actor_user_id=None,
            action=f"github.pull_request.{action}",
            target_type="project",
            target_id=str(repo.project_id),
            payload={
                "repo_id": repo_id,
                "pr_number": pr_number,
                "action": action,
                "build_id": str(build.id),
                "commit_sha": head_sha,
            },
        )

        # Commit the build record so the background builder can see it
        await db.commit()

        # Launch the built-in builder as a background task
        from app.services.builder import launch_build
        await launch_build(build.id)
        logger.info("Builder launched for PR build %s", build.id)

        return {
            "status": "build_created",
            "project_id": str(repo.project_id),
            "build_id": str(build.id),
            "pr_number": pr_number,
            "commit_sha": head_sha,
        }

    elif action == "closed":
        # PR closed — mark for cleanup (preview env teardown handled by runtime plane)
        await write_audit_log(
            db,
            actor_user_id=None,
            action="github.pull_request.closed",
            target_type="project",
            target_id=str(repo.project_id),
            payload={
                "repo_id": repo_id,
                "pr_number": pr_number,
                "merged": payload.get("pull_request", {}).get("merged", False),
            },
        )

        return {
            "status": "pr_closed",
            "project_id": str(repo.project_id),
            "pr_number": pr_number,
            "merged": payload.get("pull_request", {}).get("merged", False),
        }

    # Other PR actions (labeled, assigned, etc.) — ignore
    return {"status": "ignored", "action": action}

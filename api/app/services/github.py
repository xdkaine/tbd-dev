"""GitHub App integration service.

Handles:
- GitHub App JWT generation for API authentication
- Installation access token acquisition
- Commit status / check reporting
- Webhook signature verification
- Repository listing from App installations
"""

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone

import httpx
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


# ---------------------------------------------------------------------------
# JWT / Token helpers
# ---------------------------------------------------------------------------


def _generate_app_jwt() -> str:
    """Generate a short-lived JWT signed with the GitHub App private key.

    GitHub App JWTs are valid for up to 10 minutes. We generate one
    each time we need an installation token.
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,  # issued at (60s clock skew buffer)
        "exp": now + (9 * 60),  # expires in 9 minutes
        "iss": settings.github_app_id,
    }
    private_key = settings.github_app_private_key.replace("\\n", "\n")
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(install_id: str) -> str:
    """Exchange a GitHub App JWT for a short-lived installation access token.

    The token has the permissions granted to the App installation and is
    valid for 1 hour.
    """
    app_jwt = _generate_app_jwt()
    url = f"{GITHUB_API_BASE}/app/installations/{install_id}/access_tokens"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["token"]


# ---------------------------------------------------------------------------
# Installation management
# ---------------------------------------------------------------------------


async def list_installations() -> list[dict]:
    """List all installations of the GitHub App.

    Returns a list of installation objects with id, account info, etc.
    """
    app_jwt = _generate_app_jwt()
    installations = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                f"{GITHUB_API_BASE}/app/installations",
                params={"per_page": 100, "page": page},
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            installations.extend(data)
            page += 1

    return installations


async def list_installation_repos(install_id: str) -> list[dict]:
    """List all repositories accessible to a GitHub App installation.

    Returns a list of repository objects with id, full_name, default_branch,
    private flag, description, etc.
    """
    token = await get_installation_token(install_id)
    repos = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                f"{GITHUB_API_BASE}/installation/repositories",
                params={"per_page": 100, "page": page},
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            repo_list = data.get("repositories", [])
            if not repo_list:
                break
            repos.extend(repo_list)
            if len(repo_list) < 100:
                break
            page += 1

    return repos


async def get_repo_info(install_id: str, repo_full_name: str) -> dict | None:
    """Get info about a specific repository.

    Returns the repo object or None if not accessible.
    """
    token = await get_installation_token(install_id)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Commit status reporting
# ---------------------------------------------------------------------------

# Maps deploy state machine states to GitHub commit status states.
# GitHub supports: pending, success, failure, error
_STATE_TO_GITHUB = {
    "queued": "pending",
    "building": "pending",
    "artifact_ready": "pending",
    "provisioning": "pending",
    "healthy": "pending",
    "active": "success",
    "failed": "failure",
    "rolled_back": "failure",
    "superseded": "success",
}


async def post_commit_status(
    install_id: str,
    repo_full_name: str,
    commit_sha: str,
    state: str,
    description: str = "",
    target_url: str | None = None,
    context: str = "tbd/deploy",
) -> bool:
    """Post a commit status check to GitHub.

    Args:
        install_id: GitHub App installation ID for the repo.
        repo_full_name: owner/repo (e.g. "myorg/my-app").
        commit_sha: Full commit SHA to attach the status to.
        state: One of the deploy state machine states. Mapped to GitHub
               status values (pending/success/failure/error).
        description: Human-readable description shown in GitHub UI.
        target_url: Optional URL to the deploy/build detail page.
        context: Status context string (default "tbd/deploy").

    Returns:
        True if the status was posted successfully.
    """
    github_state = _STATE_TO_GITHUB.get(state, "pending")

    try:
        token = await get_installation_token(install_id)
    except Exception:
        logger.exception("Failed to get installation token for install %s", install_id)
        return False

    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/statuses/{commit_sha}"
    body = {
        "state": github_state,
        "description": description[:140] if description else f"Deploy {state}",
        "context": context,
    }
    if target_url:
        body["target_url"] = target_url

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json=body,
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
            logger.info(
                "Posted commit status: repo=%s sha=%s state=%s github_state=%s",
                repo_full_name,
                commit_sha[:8],
                state,
                github_state,
            )
            return True
    except Exception:
        logger.exception(
            "Failed to post commit status: repo=%s sha=%s", repo_full_name, commit_sha[:8]
        )
        return False


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


def verify_webhook_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """Verify that a webhook payload was signed by GitHub.

    Uses HMAC-SHA256 with the configured webhook secret. Returns True if
    the signature is valid or if no webhook secret is configured (dev mode).
    """
    secret = settings.github_webhook_secret
    if not secret:
        # No secret configured — skip verification (development only)
        logger.warning("Webhook signature verification skipped: no secret configured")
        return True

    if not signature_header:
        logger.warning("Webhook missing X-Hub-Signature-256 header")
        return False

    expected_sig = (
        "sha256="
        + hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected_sig, signature_header)


# ---------------------------------------------------------------------------
# OAuth token-based helpers (no GitHub App required)
# ---------------------------------------------------------------------------


async def post_commit_status_oauth(
    token: str,
    repo_full_name: str,
    commit_sha: str,
    state: str,
    description: str = "",
    target_url: str | None = None,
    context: str = "tbd/deploy",
) -> bool:
    """Post a commit status using a user's OAuth token.

    Same as post_commit_status but uses a personal OAuth token
    instead of a GitHub App installation token.
    """
    github_state = _STATE_TO_GITHUB.get(state, "pending")

    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/statuses/{commit_sha}"
    body = {
        "state": github_state,
        "description": description[:140] if description else f"Deploy {state}",
        "context": context,
    }
    if target_url:
        body["target_url"] = target_url

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            logger.info(
                "Posted commit status (OAuth): repo=%s sha=%s state=%s",
                repo_full_name,
                commit_sha[:8],
                github_state,
            )
            return True
    except Exception:
        logger.exception(
            "Failed to post commit status (OAuth): repo=%s sha=%s",
            repo_full_name,
            commit_sha[:8],
        )
        return False


async def create_repo_webhook(
    token: str,
    repo_full_name: str,
    webhook_url: str,
    secret: str | None = None,
) -> dict | None:
    """Create a webhook on a GitHub repository using the user's OAuth token.

    Creates a webhook that sends push and pull_request events to the
    specified URL. Uses the webhook secret for signature verification.

    Returns the created webhook object, or None on failure.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/hooks"
    body: dict = {
        "name": "web",
        "active": True,
        "events": ["push", "pull_request"],
        "config": {
            "url": webhook_url,
            "content_type": "json",
        },
    }
    if secret:
        body["config"]["secret"] = secret

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if resp.status_code == 422:
                # Hook already exists (GitHub returns 422 for duplicate hooks)
                logger.info("Webhook already exists for %s", repo_full_name)
                return {"status": "already_exists"}
            resp.raise_for_status()
            hook = resp.json()
            logger.info(
                "Created webhook %s on %s -> %s",
                hook.get("id"),
                repo_full_name,
                webhook_url,
            )
            return hook
    except Exception:
        logger.exception("Failed to create webhook on %s", repo_full_name)
        return None


async def get_owner_github_token(db, project_id) -> str | None:
    """Get the GitHub OAuth token of the project owner.

    Looks up project -> owner -> github_token.
    """
    from sqlalchemy import select
    from app.models.project import Project
    from app.models.user import User

    result = await db.execute(
        select(User.github_token)
        .join(Project, Project.owner_id == User.id)
        .where(Project.id == project_id)
    )
    row = result.scalar_one_or_none()
    return row


async def get_branch_head_sha(
    token: str,
    repo_full_name: str,
    branch: str = "main",
) -> str | None:
    """Fetch the HEAD commit SHA of a branch using a user's OAuth token.

    Returns the full 40-char SHA, or None on failure.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits/{branch}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            sha = data.get("sha")
            logger.info(
                "Fetched HEAD of %s/%s: %s",
                repo_full_name,
                branch,
                sha[:8] if sha else "?",
            )
            return sha
    except Exception:
        logger.exception(
            "Failed to fetch HEAD commit for %s/%s",
            repo_full_name,
            branch,
        )
        return None

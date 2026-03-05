"""Auth router - AD login, user info, and GitHub OAuth account linking."""

import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import CurrentUser, create_access_token, get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserInfo
from app.services.audit import write_audit_log
from app.services.auth import ad_auth_service
from app.services.rbac import resolve_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate against Active Directory and return a JWT token.

    1. Validate credentials against AD.
    2. Resolve user's role from AD group membership.
    3. Find or create user in the local database.
    4. Issue a JWT token.
    """
    # Authenticate against AD (offloaded to thread — ldap3 is synchronous)
    ad_user = await ad_auth_service.authenticate_async(body.username, body.password)
    if ad_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Resolve platform role from AD groups
    role = resolve_role(ad_user.groups)

    # Find or create user in local DB
    result = await db.execute(select(User).where(User.username == ad_user.username))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            username=ad_user.username,
            display_name=ad_user.display_name,
            email=ad_user.email,
            ad_dn=ad_user.dn,
        )
        db.add(user)
        await db.flush()
        logger.info("Created new user: %s (role=%s)", user.username, role.value)
    else:
        # Update user info from AD on each login
        user.display_name = ad_user.display_name
        user.email = ad_user.email
        user.ad_dn = ad_user.dn
        await db.flush()

    # Audit the login
    await write_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.login",
        target_type="user",
        target_id=str(user.id),
        payload={"role": role.value},
    )

    # Create JWT
    token, expires_in = create_access_token(user.id, user.username, role.value)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.get("/me", response_model=UserInfo)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the currently authenticated user's info."""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return UserInfo(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=current_user.role.value,
        github_username=user.github_username,
        created_at=user.created_at,
    )


# ---------- GitHub OAuth Account Linking ----------

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_API = "https://api.github.com/user"

# State tokens are short-lived JWTs (5 min) tying the OAuth flow to the logged-in user.
_STATE_EXPIRE_MINUTES = 5


def _create_oauth_state(user_id: str) -> str:
    """Create a signed state token embedding the user ID."""
    payload = {
        "sub": user_id,
        "purpose": "github_oauth",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _verify_oauth_state(state: str) -> str:
    """Verify and decode the state token. Returns user_id or raises."""
    try:
        payload = jwt.decode(state, settings.secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("purpose") != "github_oauth":
            raise ValueError("Invalid state token purpose")
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Missing sub in state token")
        return user_id
    except JWTError as exc:
        raise ValueError(f"Invalid or expired state token: {exc}") from exc


@router.get("/github")
async def github_oauth_start(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return the GitHub OAuth authorization URL for account linking.

    The frontend should redirect the user to the returned URL.
    """
    if not settings.github_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth is not configured",
        )

    state = _create_oauth_state(str(current_user.id))

    params = {
        "client_id": settings.github_client_id,
        "state": state,
        "scope": "read:user,repo",
    }
    authorize_url = f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    return {"authorize_url": authorize_url}


@router.get("/github/callback")
async def github_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """GitHub OAuth callback — exchange code for token, link account, redirect to UI."""
    # Validate state token
    try:
        user_id_str = _verify_oauth_state(state)
    except ValueError as exc:
        logger.warning("GitHub OAuth state validation failed: %s", exc)
        return RedirectResponse(
            url=f"https://{settings.ui_domain}/settings?github_error=invalid_state",
            status_code=302,
        )

    # Exchange authorization code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )

    if token_resp.status_code != 200:
        logger.error("GitHub token exchange failed: %s", token_resp.text)
        return RedirectResponse(
            url=f"https://{settings.ui_domain}/settings?github_error=token_exchange_failed",
            status_code=302,
        )

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        logger.error("No access_token in GitHub response: %s", token_data)
        return RedirectResponse(
            url=f"https://{settings.ui_domain}/settings?github_error=no_access_token",
            status_code=302,
        )

    # Fetch GitHub user profile
    async with httpx.AsyncClient() as client:
        gh_user_resp = await client.get(
            GITHUB_USER_API,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if gh_user_resp.status_code != 200:
        logger.error("GitHub user API failed: %s", gh_user_resp.text)
        return RedirectResponse(
            url=f"https://{settings.ui_domain}/settings?github_error=user_fetch_failed",
            status_code=302,
        )

    gh_user = gh_user_resp.json()
    gh_id = gh_user.get("id")
    gh_username = gh_user.get("login")

    if not gh_id or not gh_username:
        logger.error("GitHub user response missing id/login: %s", gh_user)
        return RedirectResponse(
            url=f"https://{settings.ui_domain}/settings?github_error=invalid_user_data",
            status_code=302,
        )

    # Check if this GitHub account is already linked to another user
    user_id = _uuid.UUID(user_id_str)

    existing = await db.execute(select(User).where(User.github_id == gh_id))
    existing_user = existing.scalar_one_or_none()
    if existing_user and existing_user.id != user_id:
        logger.warning(
            "GitHub account %s (%s) already linked to user %s",
            gh_username, gh_id, existing_user.username,
        )
        return RedirectResponse(
            url=f"https://{settings.ui_domain}/settings?github_error=already_linked",
            status_code=302,
        )

    # Link the GitHub account to the current user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return RedirectResponse(
            url=f"https://{settings.ui_domain}/settings?github_error=user_not_found",
            status_code=302,
        )

    user.github_id = gh_id
    user.github_username = gh_username
    user.github_token = access_token
    await db.commit()

    logger.info("Linked GitHub account %s (%s) to user %s", gh_username, gh_id, user.username)

    # Audit
    await write_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.github_link",
        target_type="user",
        target_id=str(user.id),
        payload={"github_username": gh_username, "github_id": gh_id},
    )

    return RedirectResponse(
        url=f"https://{settings.ui_domain}/settings?github_linked=true",
        status_code=302,
    )


@router.delete("/github/link", status_code=204)
async def github_unlink(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink the GitHub account from the current user."""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.github_id is None:
        raise HTTPException(status_code=400, detail="No GitHub account linked")

    old_username = user.github_username
    old_id = user.github_id

    user.github_id = None
    user.github_username = None
    user.github_token = None
    await db.commit()

    logger.info("Unlinked GitHub account %s (%s) from user %s", old_username, old_id, user.username)

    await write_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.github_unlink",
        target_type="user",
        target_id=str(user.id),
        payload={"github_username": old_username, "github_id": old_id},
    )


# ---------- User-scoped GitHub Repos (for Import flow) ----------

GITHUB_USER_REPOS_API = "https://api.github.com/user/repos"


@router.get("/github/repos")
async def list_user_github_repos(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List GitHub repositories visible to the user's linked GitHub account.

    Uses the stored OAuth token (with repo scope) to fetch the user's repos.
    Returns repos directly — no GitHub App installation lookup needed.
    """
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.github_token:
        raise HTTPException(
            status_code=400,
            detail="No GitHub account linked. Connect your GitHub account in Settings first.",
        )

    # Fetch user repos using their OAuth token (paginated)
    all_repos = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                GITHUB_USER_REPOS_API,
                params={
                    "per_page": 100,
                    "page": page,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                },
                headers={
                    "Authorization": f"Bearer {user.github_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if resp.status_code == 401:
                # Token expired or revoked — clear it
                user.github_token = None
                await db.commit()
                raise HTTPException(
                    status_code=400,
                    detail="GitHub token expired. Please re-link your GitHub account in Settings.",
                )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            all_repos.extend(data)
            if len(data) < 100:
                break
            page += 1

    # Build response — no install_id lookup needed
    items = []
    for r in all_repos:
        items.append({
            "id": r["id"],
            "full_name": r["full_name"],
            "name": r["name"],
            "private": r.get("private", False),
            "default_branch": r.get("default_branch", "main"),
            "description": r.get("description"),
            "html_url": r.get("html_url", ""),
            "install_id": None,
        })

    return items

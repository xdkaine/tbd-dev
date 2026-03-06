"""Templates router — curated starter project catalog and one-click deploy.

Endpoints:
- GET    /templates              — list all active templates (any authenticated user)
- GET    /templates/{slug}       — get template details
- POST   /templates              — admin-only: create a template catalog entry
- PATCH  /templates/{slug}       — admin-only: update a template
- DELETE /templates/{slug}       — admin-only: deactivate a template
- POST   /templates/{slug}/deploy — deploy: create repo from template + project + build
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.project import Project, Repo
from app.models.environment import Environment
from app.models.network import Quota
from app.models.template import Template
from app.models.user import User
from app.schemas.template import (
    TemplateCreate,
    TemplateDeployRequest,
    TemplateDeployResponse,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.audit import write_audit_log
from app.services.github import (
    create_repo_from_template,
    create_repo_webhook,
    get_branch_head_sha,
)
from app.services.network_allocator import auto_allocate_on_project_create
from app.services.rbac import Role, check_permission
from app.config import settings as app_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


# ---------------------------------------------------------------------------
# Public — list / get templates
# ---------------------------------------------------------------------------


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active templates, ordered by sort_order then name."""
    query = select(Template).where(Template.active.is_(True)).order_by(
        Template.sort_order, Template.name
    )
    result = await db.execute(query)
    templates = result.scalars().all()

    count_q = select(func.count()).select_from(
        select(Template.id).where(Template.active.is_(True)).subquery()
    )
    total = (await db.execute(count_q)).scalar()

    return TemplateListResponse(
        items=[TemplateResponse.model_validate(t) for t in templates],
        total=total or 0,
    )


@router.get("/{slug}", response_model=TemplateResponse)
async def get_template(
    slug: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single template by slug."""
    result = await db.execute(
        select(Template).where(Template.slug == slug, Template.active.is_(True))
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateResponse.model_validate(template)


# ---------------------------------------------------------------------------
# Admin — CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new template catalog entry (staff/faculty only)."""
    if current_user.role not in (Role.STAFF, Role.FACULTY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff and faculty can manage templates",
        )

    # Check slug uniqueness
    existing = await db.execute(select(Template).where(Template.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template with slug '{body.slug}' already exists",
        )

    template = Template(
        name=body.name,
        slug=body.slug,
        description=body.description,
        framework=body.framework,
        github_owner=body.github_owner,
        github_repo=body.github_repo,
        icon_url=body.icon_url,
        tags=body.tags,
        sort_order=body.sort_order,
    )
    db.add(template)
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="template.create",
        target_type="template",
        target_id=str(template.id),
        payload={"name": body.name, "slug": body.slug},
    )

    await db.refresh(template)
    return TemplateResponse.model_validate(template)


@router.patch("/{slug}", response_model=TemplateResponse)
async def update_template(
    slug: str,
    body: TemplateUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a template (staff/faculty only)."""
    if current_user.role not in (Role.STAFF, Role.FACULTY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff and faculty can manage templates",
        )

    result = await db.execute(select(Template).where(Template.slug == slug))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="template.update",
        target_type="template",
        target_id=str(template.id),
        payload=update_data,
    )

    await db.refresh(template)
    return TemplateResponse.model_validate(template)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    slug: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a template (soft delete, staff/faculty only)."""
    if current_user.role not in (Role.STAFF, Role.FACULTY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff and faculty can manage templates",
        )

    result = await db.execute(select(Template).where(Template.slug == slug))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    template.active = False
    await db.flush()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="template.delete",
        target_type="template",
        target_id=str(template.id),
        payload={"slug": slug},
    )


# ---------------------------------------------------------------------------
# Deploy — the main action
# ---------------------------------------------------------------------------


@router.post("/{slug}/deploy", response_model=TemplateDeployResponse)
async def deploy_template(
    slug: str,
    body: TemplateDeployRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deploy a template: create a GitHub repo from template, create a TBD project, and trigger build.

    Flow:
    1. Look up template by slug
    2. Verify user has a linked GitHub account with an OAuth token
    3. Create a new GitHub repo from the template via GitHub API
    4. Wait for repo to be ready
    5. Create a TBD project
    6. Connect the repo (which triggers initial build + deploy)
    7. Return the new project details
    """
    check_permission(current_user.role, "projects.create")

    # 1. Look up template
    result = await db.execute(
        select(Template).where(Template.slug == slug, Template.active.is_(True))
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    # 2. Verify GitHub token
    user_result = await db.execute(select(User).where(User.id == current_user.id))
    user = user_result.scalar_one_or_none()
    if not user or not user.github_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub account not linked. Connect your GitHub account first.",
        )

    # 3. Create repo from template
    try:
        new_repo = await create_repo_from_template(
            token=user.github_token,
            source_repo=app_settings.template_source_repo,
            template_path=f"templates/{template.github_repo}",
            new_repo_name=body.repo_name,
            new_repo_description=body.description,
            private=body.private,
            source_branch=app_settings.template_source_branch,
            source_token=app_settings.template_source_token or None,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    if new_repo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to create repo from template. "
                f"The repo name '{body.repo_name}' may already exist, "
                f"or the template files could not be read from the source repo."
            ),
        )

    repo_full_name = new_repo["full_name"]
    repo_html_url = new_repo.get("html_url", "")
    repo_github_id = new_repo["id"]
    default_branch = new_repo.get("default_branch", "main")

    # 4. Create TBD project (repo is immediately ready — we pushed the initial commit)
    project_slug = body.repo_name.lower().replace(".", "-").replace("_", "-")

    # Ensure slug uniqueness
    existing = await db.execute(select(Project).where(Project.slug == project_slug))
    if existing.scalar_one_or_none():
        # Append a short suffix to avoid collision
        import uuid as _uuid
        project_slug = f"{project_slug}-{str(_uuid.uuid4())[:4]}"

    project = Project(
        name=body.repo_name,
        slug=project_slug,
        repo_url=repo_html_url,
        owner_id=current_user.id,
        default_env="production",
        framework=template.framework,
    )
    db.add(project)
    await db.flush()

    # Create default environment + quota
    default_env = Environment(
        project_id=project.id,
        name="production",
        type="production",
    )
    db.add(default_env)

    quota = Quota(project_id=project.id)
    db.add(quota)

    await db.flush()

    # Auto-allocate VLAN
    try:
        await auto_allocate_on_project_create(db, project, current_user.id)
    except Exception as e:
        logger.warning(
            "VLAN auto-allocation failed for template project %s: %s",
            project.slug, e,
        )

    # 5. Connect the repo
    repo_record = Repo(
        project_id=project.id,
        provider="github",
        repo_id=str(repo_github_id),
        repo_full_name=repo_full_name,
        default_branch=default_branch,
        install_id=None,
        created_from_template=True,
        template_slug=template.slug,
    )
    db.add(repo_record)
    await db.flush()

    # Set up webhook on the new repo
    webhook_url = "https://smee.io/5yCWAJS2wt6g3Eip"
    webhook_secret = app_settings.github_webhook_secret or None
    hook = await create_repo_webhook(
        token=user.github_token,
        repo_full_name=repo_full_name,
        webhook_url=webhook_url,
        secret=webhook_secret,
    )
    if hook:
        logger.info("Webhook set up for template repo %s", repo_full_name)

    # 6. Trigger initial build
    # The commit already exists (we pushed it in create_repo_from_template),
    # so get_branch_head_sha should succeed on the first call.
    initial_build_id = None
    head_sha = await get_branch_head_sha(
        token=user.github_token,
        repo_full_name=repo_full_name,
        branch=default_branch,
    )
    if head_sha:
        from app.services.build_coordinator import create_build_for_push

        ref = f"refs/heads/{default_branch}"
        build = await create_build_for_push(db, repo_record, head_sha, ref)
        initial_build_id = build.id
        logger.info(
            "Initial build %s created for template project %s @ %s",
            build.id, repo_full_name, head_sha[:8],
        )
    else:
        logger.warning(
            "Could not fetch HEAD SHA for %s/%s — skipping initial build. "
            "The first push will trigger a build via webhook.",
            repo_full_name, default_branch,
        )

    # Audit
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="template.deploy",
        target_type="project",
        target_id=str(project.id),
        payload={
            "template_slug": slug,
            "repo_full_name": repo_full_name,
            "build_id": str(initial_build_id) if initial_build_id else None,
        },
    )

    # Commit so the background builder can see the records
    await db.commit()

    # Launch builder as background task (after commit)
    if initial_build_id:
        from app.services.builder import launch_build
        await launch_build(initial_build_id)
        logger.info("Builder launched for template build %s", initial_build_id)

    return TemplateDeployResponse(
        project_id=project.id,
        project_slug=project.slug,
        repo_full_name=repo_full_name,
        repo_html_url=repo_html_url,
        build_id=initial_build_id,
        message=f"Project created from template '{template.name}'. "
        + ("Build triggered." if initial_build_id else "Push to trigger first build."),
    )


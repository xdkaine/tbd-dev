"""Secrets router - encrypted secret management."""

import uuid

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.project import Project
from app.models.secret import Secret
from app.schemas.secret import SecretCreate, SecretListResponse, SecretResponse
from app.services.audit import write_audit_log
from app.services.rbac import Role, check_permission

router = APIRouter(prefix="/projects/{project_id}/secrets", tags=["secrets"])


def _get_fernet() -> Fernet:
    """Get Fernet encryption instance."""
    key = settings.secrets_encryption_key
    if not key:
        # Generate a key for development (in production, this MUST be set)
        key = Fernet.generate_key().decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


@router.get("", response_model=SecretListResponse)
async def list_secrets(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List secrets for a project (keys only, never values)."""
    check_permission(current_user.role, "secrets.read")

    # Verify project access
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    query = select(Secret).where(Secret.project_id == project_id)
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(Secret.key))
    secrets = result.scalars().all()

    return SecretListResponse(
        items=[SecretResponse.model_validate(s) for s in secrets],
        total=total,
    )


@router.post("", response_model=SecretResponse, status_code=status.HTTP_201_CREATED)
async def create_secret(
    project_id: uuid.UUID,
    body: SecretCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a secret."""
    check_permission(current_user.role, "secrets.create")

    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    project = proj_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Encrypt the value
    fernet = _get_fernet()
    encrypted = fernet.encrypt(body.value.encode()).decode()

    # Check if secret already exists (upsert behavior)
    existing_result = await db.execute(
        select(Secret).where(
            Secret.project_id == project_id,
            Secret.key == body.key,
            Secret.scope == body.scope,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.value_encrypted = encrypted
        await db.flush()
        secret = existing
        action = "secret.update"
    else:
        secret = Secret(
            project_id=project_id,
            scope=body.scope,
            key=body.key,
            value_encrypted=encrypted,
        )
        db.add(secret)
        await db.flush()
        action = "secret.create"

    # Audit (never log the value)
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action=action,
        target_type="secret",
        target_id=str(secret.id),
        payload={"project_id": str(project_id), "key": body.key, "scope": body.scope},
    )

    return SecretResponse.model_validate(secret)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(
    project_id: uuid.UUID,
    key: str,
    scope: str = "project",
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a secret by key."""
    check_permission(current_user.role, "secrets.delete")

    result = await db.execute(
        select(Secret).where(
            Secret.project_id == project_id,
            Secret.key == key,
            Secret.scope == scope,
        )
    )
    secret = result.scalar_one_or_none()
    if secret is None:
        raise HTTPException(status_code=404, detail="Secret not found")

    # Audit
    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="secret.delete",
        target_type="secret",
        target_id=str(secret.id),
        payload={"project_id": str(project_id), "key": key, "scope": scope},
    )

    await db.delete(secret)
    await db.flush()

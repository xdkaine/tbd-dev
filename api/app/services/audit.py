"""Audit logging service."""

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


async def write_audit_log(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict | None = None,
) -> AuditLog:
    """Write an entry to the audit log.

    Args:
        db: Database session.
        actor_user_id: UUID of the user performing the action (None for system actions).
        action: Action identifier, e.g. 'project.create', 'deploy.rollback'.
        target_type: Type of target, e.g. 'project', 'deploy', 'secret'.
        target_id: ID of the target resource.
        payload: Optional JSON-serializable dict with additional context.
    """
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        payload=json.dumps(payload) if payload else None,
    )
    db.add(entry)
    await db.flush()

    logger.info(
        "Audit: actor=%s action=%s target=%s/%s",
        actor_user_id,
        action,
        target_type,
        target_id,
    )

    return entry

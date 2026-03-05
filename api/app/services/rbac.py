"""RBAC service - maps AD groups to platform roles and enforces permissions."""

import logging
from enum import Enum

from app.config import settings

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """Platform roles mapped from AD groups."""

    DEVELOPER = "JAS_Developer"
    STAFF = "JAS-Staff"
    FACULTY = "JAS-Faculty"


# Permission definitions per role
# Faculty has all permissions, Staff has operational permissions, Developer has self-service
ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.DEVELOPER: {
        "projects.read",
        "projects.create",
        "projects.update.own",
        "projects.delete.own",
        "projects.members.read.own",
        "projects.members.manage.own",
        "users.search",
        "environments.read",
        "environments.create",
        "builds.read",
        "builds.create",
        "deploys.read",
        "deploys.create",
        "deploys.rollback.own",
        "deploys.destroy.own",
        "deploys.container.own",  # start/stop own containers
        "secrets.read.own",
        "secrets.create.own",
        "secrets.delete.own",
        "audit.read.own",
    },
    Role.STAFF: {
        "projects.read",
        "projects.create",
        "projects.update",
        "projects.delete",
        "projects.members.read",
        "projects.members.manage",
        "users.search",
        "environments.read",
        "environments.create",
        "environments.delete",
        "builds.read",
        "builds.create",
        "deploys.read",
        "deploys.create",
        "deploys.rollback",
        "deploys.destroy",
        "deploys.container",  # start/stop any container
        "secrets.read",
        "secrets.create",
        "secrets.delete",
        "networks.read",
        "networks.reserve",
        "quotas.read",
        "users.read",
        "audit.read",
    },
    Role.FACULTY: {
        "projects.read",
        "projects.create",
        "projects.update",
        "projects.delete",
        "projects.members.read",
        "projects.members.manage",
        "users.search",
        "environments.read",
        "environments.create",
        "environments.delete",
        "builds.read",
        "builds.create",
        "deploys.read",
        "deploys.create",
        "deploys.rollback",
        "deploys.destroy",
        "deploys.container",  # start/stop any container
        "secrets.read",
        "secrets.create",
        "secrets.delete",
        "networks.read",
        "networks.reserve",
        "networks.configure",
        "quotas.read",
        "quotas.update",
        "audit.read",
        "users.read",
        "users.manage",
    },
}

# Map AD group names to roles
GROUP_ROLE_MAP: dict[str, Role] = {
    settings.ad_developer_group: Role.DEVELOPER,
    settings.ad_staff_group: Role.STAFF,
    settings.ad_faculty_group: Role.FACULTY,
}


def resolve_role(ad_groups: list[str]) -> Role:
    """Determine the highest-privilege role from a user's AD group memberships.

    Priority: faculty > staff > developer.
    Defaults to developer if no matching group is found.
    """
    role = Role.DEVELOPER

    for group_name in ad_groups:
        mapped_role = GROUP_ROLE_MAP.get(group_name)
        if mapped_role is None:
            continue
        if mapped_role == Role.FACULTY:
            return Role.FACULTY
        if mapped_role == Role.STAFF:
            role = Role.STAFF

    return role


def has_permission(role: Role, permission: str) -> bool:
    """Check if a role has a specific permission."""
    permissions = ROLE_PERMISSIONS.get(role, set())
    return permission in permissions


def check_permission(role: Role, permission: str) -> None:
    """Check permission and raise if denied.

    For '.own' permissions, the caller must additionally verify ownership.
    This function checks if either the exact permission or the '.own' variant exists.
    """
    permissions = ROLE_PERMISSIONS.get(role, set())

    if permission in permissions:
        return

    # Check if the role has the '.own' variant (ownership check done by caller)
    own_permission = f"{permission}.own"
    if own_permission in permissions:
        return

    from fastapi import HTTPException, status

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Insufficient permissions: '{permission}' required",
    )

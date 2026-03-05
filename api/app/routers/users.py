"""Users router - admin user management.

Faculty can view all users and manage role assignments.
Staff can view users.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.project import Project
from app.models.user import Group, GroupRoleMap, User
from app.schemas.user import UserListResponse, UserResponse, UserRoleUpdate
from app.services.audit import write_audit_log
from app.services.rbac import Role, check_permission

router = APIRouter(prefix="/admin/users", tags=["admin", "users"])


@router.get("", response_model=UserListResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, description="Search by username or display name"),
    role: str | None = Query(None, description="Filter by role"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all platform users with their project counts.

    Requires users.read permission (Staff/Faculty).
    """
    check_permission(current_user.role, "users.read")

    # Base query
    query = select(User)

    if search:
        query = query.where(
            User.username.ilike(f"%{search}%") | User.display_name.ilike(f"%{search}%")
        )

    # Fetch all search-matched users (no SQL pagination yet — we need to
    # resolve roles first to apply the role filter correctly)
    result = await db.execute(query.order_by(User.username))
    users = result.scalars().all()

    # Get project counts for all users in one batch query
    project_counts_result = await db.execute(
        select(Project.owner_id, func.count(Project.id))
        .group_by(Project.owner_id)
    )
    project_counts = dict(project_counts_result.all())

    # Batch-resolve all user roles in a single query (avoids N+1)
    role_overrides = await _resolve_user_roles_batch(db, users)

    # Build full list with role info, then apply role filter
    all_items = []
    for u in users:
        user_role = role_overrides.get(u.username, Role.DEVELOPER.value)
        if role and user_role != role:
            continue
        all_items.append(
            UserResponse(
                id=u.id,
                username=u.username,
                display_name=u.display_name,
                email=u.email,
                role=user_role,
                github_username=u.github_username,
                project_count=project_counts.get(u.id, 0),
                created_at=u.created_at,
            )
        )

    # Now apply pagination to the fully-filtered list
    total = len(all_items)
    items = all_items[skip : skip + limit]

    return UserListResponse(items=items, total=total)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific user's details."""
    check_permission(current_user.role, "users.read")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Get project count
    count_result = await db.execute(
        select(func.count(Project.id)).where(Project.owner_id == user_id)
    )
    project_count = count_result.scalar()

    user_role = await _resolve_user_role(db, user)

    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user_role,
        github_username=user.github_username,
        project_count=project_count,
        created_at=user.created_at,
    )


@router.patch("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: uuid.UUID,
    body: UserRoleUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's platform role (Faculty only).

    This creates/updates the GroupRoleMap to override the user's
    role without changing their AD group membership.
    """
    check_permission(current_user.role, "users.manage")

    # Cannot change your own role
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = await _resolve_user_role(db, user)

    # Find or create a group for this user's role override
    override_group_name = f"override_{user.username}"
    group_result = await db.execute(
        select(Group).where(Group.name == override_group_name)
    )
    group = group_result.scalar_one_or_none()

    if group is None:
        group = Group(name=override_group_name, ad_dn=f"CN={override_group_name},OU=Overrides")
        db.add(group)
        await db.flush()

    # Update or create the role mapping
    role_map_result = await db.execute(
        select(GroupRoleMap).where(GroupRoleMap.group_id == group.id)
    )
    role_map = role_map_result.scalar_one_or_none()

    if role_map is None:
        role_map = GroupRoleMap(group_id=group.id, role=body.role)
        db.add(role_map)
    else:
        role_map.role = body.role

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="user.role.update",
        target_type="user",
        target_id=str(user_id),
        payload={"from": old_role, "to": body.role, "username": user.username},
    )

    await db.commit()

    # Get project count
    count_result = await db.execute(
        select(func.count(Project.id)).where(Project.owner_id == user_id)
    )
    project_count = count_result.scalar()

    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=body.role,
        github_username=user.github_username,
        project_count=project_count,
        created_at=user.created_at,
    )


async def _resolve_user_roles_batch(
    db: AsyncSession, users: list[User]
) -> dict[str, str]:
    """Batch-resolve effective roles for a list of users.

    Returns a dict mapping username -> role string. Users without
    an override default to JAS_Developer.
    """
    if not users:
        return {}

    # Build override group names for all users
    usernames = [u.username for u in users]
    override_names = [f"override_{uname}" for uname in usernames]

    # Single query: join GroupRoleMap -> Group, filter by override names
    result = await db.execute(
        select(Group.name, GroupRoleMap.role)
        .join(Group, GroupRoleMap.group_id == Group.id)
        .where(Group.name.in_(override_names))
    )
    overrides_raw = result.all()

    # Map "override_<username>" back to username -> role
    overrides: dict[str, str] = {}
    for group_name, role_val in overrides_raw:
        username = group_name.removeprefix("override_")
        overrides[username] = role_val

    return overrides


async def _resolve_user_role(db: AsyncSession, user: User) -> str:
    """Resolve a single user's effective role (used by get/update endpoints)."""
    result = await _resolve_user_roles_batch(db, [user])
    return result.get(user.username, Role.DEVELOPER.value)

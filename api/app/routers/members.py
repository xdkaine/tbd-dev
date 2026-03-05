"""Project members router — add, list, and remove contributors.

Also provides a lightweight user search endpoint so that any authenticated
user can find people to add to their projects (the admin user list requires
elevated permissions).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.members import (
    ProjectMemberAdd,
    ProjectMemberListResponse,
    ProjectMemberResponse,
    UserSearchResponse,
    UserSearchResult,
)
from app.services.audit import write_audit_log
from app.services.rbac import Role, check_permission

logger = logging.getLogger(__name__)

router = APIRouter(tags=["members"])


# ---------- Lightweight user search (all authenticated users) ----------


@router.get("/users/search", response_model=UserSearchResponse)
async def search_users(
    q: str = Query(..., min_length=1, max_length=255, description="Search term"),
    limit: int = Query(20, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for users by username or display name.

    Available to all authenticated users so they can find people to add to
    projects.  Returns minimal fields (no email, no role) for privacy.
    """
    term = f"%{q}%"
    query = select(User).where(
        or_(
            User.username.ilike(term),
            User.display_name.ilike(term),
        )
    )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(User.username).limit(limit))
    users = result.scalars().all()

    return UserSearchResponse(
        items=[
            UserSearchResult(
                id=u.id,
                username=u.username,
                display_name=u.display_name,
                email=u.email,
            )
            for u in users
        ],
        total=total,
    )


# ---------- Project member helpers ----------


async def _get_project_for_member_mgmt(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession,
) -> Project:
    """Load a project and verify the current user is the owner (or staff/faculty).

    Only owners can manage members.  Staff/Faculty can manage any project's
    members.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if current_user.role == Role.DEVELOPER and project.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the project owner can manage members"
        )

    return project


# ---------- Member endpoints ----------


@router.get(
    "/projects/{project_id}/members",
    response_model=ProjectMemberListResponse,
)
async def list_members(
    project_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all members of a project.

    Visible to the owner, any contributor, and staff/faculty.
    """
    check_permission(current_user.role, "projects.read")

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Developers must be owner or a member to see the member list
    if current_user.role == Role.DEVELOPER:
        is_member = await db.execute(
            select(ProjectMember.id).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == current_user.id,
            )
        )
        if project.owner_id != current_user.id and is_member.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Project not found")

    # Fetch members joined with user info
    query = (
        select(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    )
    rows = (await db.execute(query)).all()

    items = [
        ProjectMemberResponse(
            id=member.id,
            project_id=member.project_id,
            user_id=member.user_id,
            role=member.role,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            created_at=member.created_at,
        )
        for member, user in rows
    ]

    return ProjectMemberListResponse(items=items, total=len(items))


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    project_id: uuid.UUID,
    body: ProjectMemberAdd,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a user as a contributor to a project.

    Race-condition safe: the unique constraint on (project_id, user_id)
    prevents duplicate memberships even under concurrent requests.
    """
    project = await _get_project_for_member_mgmt(project_id, current_user, db)

    # Cannot add the owner as a member — they already have full access
    if body.user_id == project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The project owner cannot be added as a member",
        )

    # Verify target user exists
    user_result = await db.execute(select(User).where(User.id == body.user_id))
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    member = ProjectMember(
        project_id=project_id,
        user_id=body.user_id,
        role=body.role,
    )
    db.add(member)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        # Race condition — the user was already added by someone else
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this project",
        )

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="project.member.add",
        target_type="project",
        target_id=str(project_id),
        payload={
            "user_id": str(body.user_id),
            "username": target_user.username,
            "role": body.role,
        },
    )

    return ProjectMemberResponse(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        username=target_user.username,
        display_name=target_user.display_name,
        email=target_user.email,
        created_at=member.created_at,
    )


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a contributor from a project.

    Allowed for the project owner, the member themselves (leave), and
    staff/faculty.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Developers can remove if they are the owner or removing themselves
    if current_user.role == Role.DEVELOPER:
        if project.owner_id != current_user.id and user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Only the project owner can remove members",
            )

    member_result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = member_result.scalar_one_or_none()

    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    # Look up the user for audit purposes
    user_result = await db.execute(select(User).where(User.id == user_id))
    target_user = user_result.scalar_one_or_none()

    await write_audit_log(
        db,
        actor_user_id=current_user.id,
        action="project.member.remove",
        target_type="project",
        target_id=str(project_id),
        payload={
            "user_id": str(user_id),
            "username": target_user.username if target_user else str(user_id),
        },
    )

    await db.delete(member)
    await db.flush()

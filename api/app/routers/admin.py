"""Admin router - platform statistics, trends, activity, projects, and students.

Provides Staff and Faculty with supervisory views of the entire platform.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, cast, func, or_, select, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser, get_current_user
from app.models.audit import AuditLog
from app.models.build import Build
from app.models.deploy import Deploy
from app.models.environment import Environment
from app.models.network import Quota, Vlan
from app.models.network_policy import NetworkPolicy
from app.models.project import Project, ProjectMember, Repo
from app.models.user import User
from app.services.rbac import Role, check_permission

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
#  Schemas
# ---------------------------------------------------------------------------

class AdminStats(BaseModel):
    """Platform-wide statistics for the admin dashboard."""

    total_users: int
    total_projects: int
    total_deploys: int
    active_deploys: int
    total_builds: int
    vlans_allocated: int
    vlans_available: int
    total_network_policies: int


class TrendPoint(BaseModel):
    """A single data point in a time-series trend."""
    date: str  # ISO date string YYYY-MM-DD
    deploys: int
    builds: int
    failed_deploys: int
    failed_builds: int


class TrendResponse(BaseModel):
    """Daily deploy/build counts for trend charts."""
    points: list[TrendPoint]
    period_days: int


class ActivityEvent(BaseModel):
    """A recent platform activity event for the activity feed."""
    id: str
    type: str  # "deploy" | "build" | "project.create" | "project.delete" | "user.role.update"
    timestamp: str
    actor_name: str | None
    actor_username: str | None
    project_name: str | None
    project_id: str | None
    status: str | None
    detail: str | None


class ActivityResponse(BaseModel):
    """Recent platform activity feed."""
    items: list[ActivityEvent]
    total: int


class AdminProjectItem(BaseModel):
    """A project in the admin all-projects listing."""
    id: str
    name: str
    slug: str
    owner_id: str
    owner_username: str
    owner_display_name: str
    framework: str | None
    repo_url: str | None
    repo_full_name: str | None
    production_url: str | None
    deploy_locked: bool
    expires_at: str | None
    created_at: str
    latest_deploy_status: str | None
    total_deploys: int
    total_builds: int
    member_count: int
    tags: list[str]


class AdminProjectListResponse(BaseModel):
    """Paginated list of all platform projects."""
    items: list[AdminProjectItem]
    total: int


class StudentSummary(BaseModel):
    """A student (developer) in the admin students listing."""
    id: str
    username: str
    display_name: str
    email: str
    role: str
    github_username: str | None
    created_at: str
    project_count: int
    total_builds: int
    total_deploys: int
    active_deploys: int
    last_activity: str | None  # ISO timestamp of most recent build or deploy


class StudentListResponse(BaseModel):
    """Paginated list of students."""
    items: list[StudentSummary]
    total: int


class StudentDetail(BaseModel):
    """Detailed student info with project breakdown."""
    id: str
    username: str
    display_name: str
    email: str
    role: str
    github_username: str | None
    created_at: str
    projects: list[AdminProjectItem]
    total_builds: int
    total_deploys: int
    active_deploys: int
    failed_deploys: int
    success_rate: float  # 0-100
    last_activity: str | None


# ---------------------------------------------------------------------------
#  GET /admin/stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get platform-wide statistics for the admin dashboard.

    Requires audit.read permission (Staff/Faculty).
    """
    check_permission(current_user.role, "audit.read")

    users_count = await db.execute(select(func.count(User.id)))
    projects_count = await db.execute(select(func.count(Project.id)))
    deploys_count = await db.execute(select(func.count(Deploy.id)))
    active_deploys_count = await db.execute(
        select(func.count(Deploy.id)).where(Deploy.status == "active")
    )
    builds_count = await db.execute(select(func.count(Build.id)))
    vlans_allocated_count = await db.execute(
        select(func.count(Vlan.id)).where(Vlan.reserved_by_project_id.isnot(None))
    )
    vlans_available_count = await db.execute(
        select(func.count(Vlan.id)).where(Vlan.reserved_by_project_id.is_(None))
    )
    policies_count = await db.execute(select(func.count(NetworkPolicy.id)))

    return AdminStats(
        total_users=users_count.scalar() or 0,
        total_projects=projects_count.scalar() or 0,
        total_deploys=deploys_count.scalar() or 0,
        active_deploys=active_deploys_count.scalar() or 0,
        total_builds=builds_count.scalar() or 0,
        vlans_allocated=vlans_allocated_count.scalar() or 0,
        vlans_available=vlans_available_count.scalar() or 0,
        total_network_policies=policies_count.scalar() or 0,
    )


# ---------------------------------------------------------------------------
#  GET /admin/stats/trends
# ---------------------------------------------------------------------------

@router.get("/stats/trends", response_model=TrendResponse)
async def get_admin_trends(
    days: int = Query(30, ge=7, le=90),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get daily deploy/build counts for trend charts.

    Requires audit.read permission (Staff/Faculty).
    """
    check_permission(current_user.role, "audit.read")

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Daily deploy counts
    deploy_q = (
        select(
            cast(Deploy.created_at, Date).label("day"),
            func.count(Deploy.id).label("total"),
            func.count(
                case((Deploy.status == "failed", Deploy.id))
            ).label("failed"),
        )
        .where(Deploy.created_at >= since)
        .group_by(cast(Deploy.created_at, Date))
    )
    deploy_rows = await db.execute(deploy_q)
    deploy_by_day = {str(r.day): (r.total, r.failed) for r in deploy_rows}

    # Daily build counts
    build_q = (
        select(
            cast(Build.started_at, Date).label("day"),
            func.count(Build.id).label("total"),
            func.count(
                case((Build.status == "failed", Build.id))
            ).label("failed"),
        )
        .where(Build.started_at >= since)
        .group_by(cast(Build.started_at, Date))
    )
    build_rows = await db.execute(build_q)
    build_by_day = {str(r.day): (r.total, r.failed) for r in build_rows}

    # Build the points array for every day in range
    points = []
    for i in range(days):
        day = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        d_total, d_failed = deploy_by_day.get(day, (0, 0))
        b_total, b_failed = build_by_day.get(day, (0, 0))
        points.append(TrendPoint(
            date=day,
            deploys=d_total,
            builds=b_total,
            failed_deploys=d_failed,
            failed_builds=b_failed,
        ))

    return TrendResponse(points=points, period_days=days)


# ---------------------------------------------------------------------------
#  GET /admin/activity
# ---------------------------------------------------------------------------

@router.get("/activity", response_model=ActivityResponse)
async def get_admin_activity(
    limit: int = Query(30, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent platform activity for the activity feed.

    Returns the most recent deploys, builds, and audit events combined
    into a unified chronological feed.

    Requires audit.read permission (Staff/Faculty).
    """
    check_permission(current_user.role, "audit.read")

    events: list[ActivityEvent] = []

    # Recent deploys (with project info)
    deploy_q = (
        select(Deploy, Environment, Project, User)
        .join(Environment, Deploy.env_id == Environment.id)
        .join(Project, Environment.project_id == Project.id)
        .join(User, Project.owner_id == User.id)
        .order_by(Deploy.created_at.desc())
        .limit(limit)
    )
    deploy_rows = await db.execute(deploy_q)
    for deploy, env, project, owner in deploy_rows:
        events.append(ActivityEvent(
            id=str(deploy.id),
            type="deploy",
            timestamp=deploy.created_at.isoformat(),
            actor_name=owner.display_name,
            actor_username=owner.username,
            project_name=project.name,
            project_id=str(project.id),
            status=deploy.status,
            detail=f"{env.name} ({env.type})",
        ))

    # Recent builds (with project info)
    build_q = (
        select(Build, Project, User)
        .join(Project, Build.project_id == Project.id)
        .join(User, Project.owner_id == User.id)
        .order_by(Build.started_at.desc().nullslast())
        .limit(limit)
    )
    build_rows = await db.execute(build_q)
    for build, project, owner in build_rows:
        ts = build.started_at or build.finished_at
        if ts:
            events.append(ActivityEvent(
                id=str(build.id),
                type="build",
                timestamp=ts.isoformat(),
                actor_name=owner.display_name,
                actor_username=owner.username,
                project_name=project.name,
                project_id=str(project.id),
                status=build.status,
                detail=f"{build.trigger} — {build.branch or 'main'}",
            ))

    # Recent audit events (project.create, project.delete, user.role.update)
    audit_q = (
        select(AuditLog, User)
        .outerjoin(User, AuditLog.actor_user_id == User.id)
        .where(AuditLog.action.in_([
            "project.create", "project.delete", "user.role.update",
        ]))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    audit_rows = await db.execute(audit_q)
    for entry, actor in audit_rows:
        events.append(ActivityEvent(
            id=str(entry.id),
            type=entry.action,
            timestamp=entry.created_at.isoformat(),
            actor_name=actor.display_name if actor else None,
            actor_username=actor.username if actor else None,
            project_name=None,
            project_id=entry.target_id if entry.target_type == "project" else None,
            status=None,
            detail=entry.payload,
        ))

    # Sort by timestamp descending and trim to limit
    events.sort(key=lambda e: e.timestamp, reverse=True)
    events = events[:limit]

    return ActivityResponse(items=events, total=len(events))


# ---------------------------------------------------------------------------
#  GET /admin/projects  — all projects with owner info & stats
# ---------------------------------------------------------------------------

@router.get("/projects", response_model=AdminProjectListResponse)
async def list_all_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, description="Search by project name or owner"),
    status: str | None = Query(None, description="Filter by latest deploy status"),
    tag: str | None = Query(None, description="Filter by tag name"),
    sort: str = Query("created_at", description="Sort field: created_at, name, owner, deploys"),
    order: str = Query("desc", description="Sort order: asc, desc"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List ALL platform projects with owner info and deployment stats.

    Available to Staff and Faculty for supervisory views.
    Requires audit.read permission.
    """
    check_permission(current_user.role, "audit.read")

    # Base query: projects + owner
    query = (
        select(Project, User)
        .join(User, Project.owner_id == User.id)
    )

    if search:
        query = query.where(
            or_(
                Project.name.ilike(f"%{search}%"),
                Project.slug.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                User.display_name.ilike(f"%{search}%"),
            )
        )

    # Count total (before pagination)
    count_q = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    # Sort
    sort_map = {
        "created_at": Project.created_at,
        "name": Project.name,
        "owner": User.username,
    }
    sort_col = sort_map.get(sort, Project.created_at)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    result = await db.execute(query.offset(skip).limit(limit))
    rows = result.all()

    # Batch-load stats for these projects
    project_ids = [p.id for p, _ in rows]

    if project_ids:
        # Deploy counts + latest status per project
        deploy_stats_q = (
            select(
                Environment.project_id,
                func.count(Deploy.id).label("total"),
                func.count(case((Deploy.status == "active", Deploy.id))).label("active"),
            )
            .join(Deploy, Environment.id == Deploy.env_id)
            .where(Environment.project_id.in_(project_ids))
            .group_by(Environment.project_id)
        )
        deploy_stats = await db.execute(deploy_stats_q)
        deploy_map = {
            r.project_id: (r.total, r.active)
            for r in deploy_stats
        }

        # Latest deploy status per project
        latest_deploy_q = (
            select(
                Environment.project_id,
                Deploy.status,
                func.row_number().over(
                    partition_by=Environment.project_id,
                    order_by=Deploy.created_at.desc(),
                ).label("rn"),
            )
            .join(Deploy, Environment.id == Deploy.env_id)
            .where(Environment.project_id.in_(project_ids))
        ).subquery()
        latest_q = select(
            latest_deploy_q.c.project_id,
            latest_deploy_q.c.status,
        ).where(latest_deploy_q.c.rn == 1)
        latest_rows = await db.execute(latest_q)
        latest_status_map = {r.project_id: r.status for r in latest_rows}

        # Build counts per project
        build_stats_q = (
            select(
                Build.project_id,
                func.count(Build.id).label("total"),
            )
            .where(Build.project_id.in_(project_ids))
            .group_by(Build.project_id)
        )
        build_stats = await db.execute(build_stats_q)
        build_map = {r.project_id: r.total for r in build_stats}

        # Member counts per project
        member_stats_q = (
            select(
                ProjectMember.project_id,
                func.count(ProjectMember.id).label("total"),
            )
            .where(ProjectMember.project_id.in_(project_ids))
            .group_by(ProjectMember.project_id)
        )
        member_stats = await db.execute(member_stats_q)
        member_map = {r.project_id: r.total for r in member_stats}
    else:
        deploy_map = {}
        latest_status_map = {}
        build_map = {}
        member_map = {}

    # Filter by deploy status if requested
    items = []
    for project, owner in rows:
        latest = latest_status_map.get(project.id)
        if status and latest != status:
            continue

        d_total, _ = deploy_map.get(project.id, (0, 0))
        items.append(AdminProjectItem(
            id=str(project.id),
            name=project.name,
            slug=project.slug,
            owner_id=str(project.owner_id),
            owner_username=owner.username,
            owner_display_name=owner.display_name,
            framework=project.framework,
            repo_url=project.repo_url,
            repo_full_name=project.repo.repo_full_name if project.repo else None,
            production_url=project.production_url,
            deploy_locked=project.deploy_locked,
            expires_at=project.expires_at.isoformat() if project.expires_at else None,
            created_at=project.created_at.isoformat(),
            latest_deploy_status=latest,
            total_deploys=d_total,
            total_builds=build_map.get(project.id, 0),
            member_count=member_map.get(project.id, 0),
            tags=[],  # Tags will be populated after Phase 2 (tags model)
        ))

    return AdminProjectListResponse(items=items, total=total)


# ---------------------------------------------------------------------------
#  GET /admin/students  — all developer users with activity stats
# ---------------------------------------------------------------------------

@router.get("/students", response_model=StudentListResponse)
async def list_students(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, description="Search by username or display name"),
    sort: str = Query("last_activity", description="Sort: last_activity, name, projects, deploys"),
    order: str = Query("desc", description="Sort order: asc, desc"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all platform users with project and activity statistics.

    Available to Staff and Faculty for the students view.
    Requires users.read permission.
    """
    check_permission(current_user.role, "users.read")

    # Fetch all users
    user_q = select(User)
    if search:
        user_q = user_q.where(
            or_(
                User.username.ilike(f"%{search}%"),
                User.display_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            )
        )

    result = await db.execute(user_q.order_by(User.username))
    all_users = result.scalars().all()

    # Batch-resolve roles
    from app.routers.users import _resolve_user_roles_batch
    role_overrides = await _resolve_user_roles_batch(db, all_users)

    # Batch stats: project counts per owner
    proj_counts_q = (
        select(Project.owner_id, func.count(Project.id))
        .group_by(Project.owner_id)
    )
    proj_counts = dict((await db.execute(proj_counts_q)).all())

    # Batch stats: build counts per project owner
    build_counts_q = (
        select(Project.owner_id, func.count(Build.id))
        .join(Build, Build.project_id == Project.id)
        .group_by(Project.owner_id)
    )
    build_counts = dict((await db.execute(build_counts_q)).all())

    # Batch stats: deploy counts per project owner
    deploy_counts_q = (
        select(Project.owner_id, func.count(Deploy.id))
        .join(Environment, Environment.project_id == Project.id)
        .join(Deploy, Deploy.env_id == Environment.id)
        .group_by(Project.owner_id)
    )
    deploy_counts = dict((await db.execute(deploy_counts_q)).all())

    # Active deploy counts per project owner
    active_deploy_q = (
        select(Project.owner_id, func.count(Deploy.id))
        .join(Environment, Environment.project_id == Project.id)
        .join(Deploy, Deploy.env_id == Environment.id)
        .where(Deploy.status == "active")
        .group_by(Project.owner_id)
    )
    active_deploy_counts = dict((await db.execute(active_deploy_q)).all())

    # Last activity (most recent deploy or build) per owner
    last_deploy_q = (
        select(Project.owner_id, func.max(Deploy.created_at).label("ts"))
        .join(Environment, Environment.project_id == Project.id)
        .join(Deploy, Deploy.env_id == Environment.id)
        .group_by(Project.owner_id)
    )
    last_deploy = dict((await db.execute(last_deploy_q)).all())

    last_build_q = (
        select(Project.owner_id, func.max(Build.started_at).label("ts"))
        .join(Build, Build.project_id == Project.id)
        .group_by(Project.owner_id)
    )
    last_build = dict((await db.execute(last_build_q)).all())

    # Build items
    items = []
    for u in all_users:
        user_role = role_overrides.get(u.username, Role.DEVELOPER.value)
        ld = last_deploy.get(u.id)
        lb = last_build.get(u.id)
        last_act = max(filter(None, [ld, lb]), default=None)

        items.append(StudentSummary(
            id=str(u.id),
            username=u.username,
            display_name=u.display_name,
            email=u.email,
            role=user_role,
            github_username=u.github_username,
            created_at=u.created_at.isoformat(),
            project_count=proj_counts.get(u.id, 0),
            total_builds=build_counts.get(u.id, 0),
            total_deploys=deploy_counts.get(u.id, 0),
            active_deploys=active_deploy_counts.get(u.id, 0),
            last_activity=last_act.isoformat() if last_act else None,
        ))

    # Sort
    if sort == "name":
        items.sort(key=lambda s: s.display_name.lower(), reverse=(order == "desc"))
    elif sort == "projects":
        items.sort(key=lambda s: s.project_count, reverse=(order == "desc"))
    elif sort == "deploys":
        items.sort(key=lambda s: s.total_deploys, reverse=(order == "desc"))
    else:  # last_activity
        items.sort(
            key=lambda s: s.last_activity or "",
            reverse=(order == "desc"),
        )

    total = len(items)
    items = items[skip: skip + limit]

    return StudentListResponse(items=items, total=total)


# ---------------------------------------------------------------------------
#  GET /admin/students/{user_id}  — single student detail
# ---------------------------------------------------------------------------

@router.get("/students/{user_id}", response_model=StudentDetail)
async def get_student_detail(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info for a single student/user including all their projects.

    Requires users.read permission (Staff/Faculty).
    """
    check_permission(current_user.role, "users.read")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Resolve role
    from app.routers.users import _resolve_user_role
    user_role = await _resolve_user_role(db, user)

    # Get this user's projects
    projects_q = (
        select(Project)
        .where(Project.owner_id == user_id)
        .order_by(Project.created_at.desc())
    )
    projects_result = await db.execute(projects_q)
    projects = projects_result.scalars().all()

    project_ids = [p.id for p in projects]

    # Stats for each project
    if project_ids:
        deploy_stats_q = (
            select(
                Environment.project_id,
                func.count(Deploy.id).label("total"),
            )
            .join(Deploy, Environment.id == Deploy.env_id)
            .where(Environment.project_id.in_(project_ids))
            .group_by(Environment.project_id)
        )
        deploy_stats = dict(
            (r.project_id, r.total)
            for r in (await db.execute(deploy_stats_q))
        )

        latest_deploy_q = (
            select(
                Environment.project_id,
                Deploy.status,
                func.row_number().over(
                    partition_by=Environment.project_id,
                    order_by=Deploy.created_at.desc(),
                ).label("rn"),
            )
            .join(Deploy, Environment.id == Deploy.env_id)
            .where(Environment.project_id.in_(project_ids))
        ).subquery()
        latest_q = select(
            latest_deploy_q.c.project_id,
            latest_deploy_q.c.status,
        ).where(latest_deploy_q.c.rn == 1)
        latest_rows = await db.execute(latest_q)
        latest_map = {r.project_id: r.status for r in latest_rows}

        build_stats_q = (
            select(Build.project_id, func.count(Build.id))
            .where(Build.project_id.in_(project_ids))
            .group_by(Build.project_id)
        )
        build_stats = dict((await db.execute(build_stats_q)).all())

        member_stats_q = (
            select(ProjectMember.project_id, func.count(ProjectMember.id))
            .where(ProjectMember.project_id.in_(project_ids))
            .group_by(ProjectMember.project_id)
        )
        member_stats = dict((await db.execute(member_stats_q)).all())
    else:
        deploy_stats = {}
        latest_map = {}
        build_stats = {}
        member_stats = {}

    project_items = []
    for p in projects:
        project_items.append(AdminProjectItem(
            id=str(p.id),
            name=p.name,
            slug=p.slug,
            owner_id=str(p.owner_id),
            owner_username=user.username,
            owner_display_name=user.display_name,
            framework=p.framework,
            repo_url=p.repo_url,
            repo_full_name=p.repo.repo_full_name if p.repo else None,
            production_url=p.production_url,
            deploy_locked=p.deploy_locked,
            expires_at=p.expires_at.isoformat() if p.expires_at else None,
            created_at=p.created_at.isoformat(),
            latest_deploy_status=latest_map.get(p.id),
            total_deploys=deploy_stats.get(p.id, 0),
            total_builds=build_stats.get(p.id, 0),
            member_count=member_stats.get(p.id, 0),
            tags=[],
        ))

    # Aggregate stats
    total_builds = sum(build_stats.get(p.id, 0) for p in projects)
    total_deploys = sum(deploy_stats.get(p.id, 0) for p in projects)

    # Active & failed counts
    if project_ids:
        active_q = (
            select(func.count(Deploy.id))
            .join(Environment, Deploy.env_id == Environment.id)
            .where(Environment.project_id.in_(project_ids), Deploy.status == "active")
        )
        active_result = await db.execute(active_q)
        active_count = active_result.scalar() or 0

        failed_q = (
            select(func.count(Deploy.id))
            .join(Environment, Deploy.env_id == Environment.id)
            .where(Environment.project_id.in_(project_ids), Deploy.status == "failed")
        )
        failed_result = await db.execute(failed_q)
        failed_count = failed_result.scalar() or 0
    else:
        active_count = 0
        failed_count = 0

    success_rate = 0.0
    if total_deploys > 0:
        success_rate = round((1 - (failed_count / total_deploys)) * 100, 1)

    # Last activity
    last_deploy_q = (
        select(func.max(Deploy.created_at))
        .join(Environment, Deploy.env_id == Environment.id)
        .where(Environment.project_id.in_(project_ids))
    ) if project_ids else select(func.now()).where(False)
    ld = (await db.execute(last_deploy_q)).scalar()

    last_build_q = (
        select(func.max(Build.started_at))
        .where(Build.project_id.in_(project_ids))
    ) if project_ids else select(func.now()).where(False)
    lb = (await db.execute(last_build_q)).scalar()

    last_act = max(filter(None, [ld, lb]), default=None)

    return StudentDetail(
        id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role=user_role,
        github_username=user.github_username,
        created_at=user.created_at.isoformat(),
        projects=project_items,
        total_builds=total_builds,
        total_deploys=total_deploys,
        active_deploys=active_count,
        failed_deploys=failed_count,
        success_rate=success_rate,
        last_activity=last_act.isoformat() if last_act else None,
    )

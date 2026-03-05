"""Tests for RBAC role resolution and permission checking."""

from app.services.rbac import Role, check_permission, has_permission, resolve_role


def test_resolve_role_developer():
    """Developer group yields developer role."""
    role = resolve_role(["JAS_Developer"])
    assert role == Role.DEVELOPER


def test_resolve_role_staff():
    """Staff group yields staff role."""
    role = resolve_role(["JAS-Staff"])
    assert role == Role.STAFF


def test_resolve_role_faculty():
    """Faculty group yields faculty role."""
    role = resolve_role(["JAS-Faculty"])
    assert role == Role.FACULTY


def test_resolve_role_highest_wins():
    """When user is in both staff and faculty groups, faculty wins."""
    role = resolve_role(["JAS_Developer", "JAS-Staff", "JAS-Faculty"])
    assert role == Role.FACULTY


def test_resolve_role_defaults_to_developer():
    """Unknown groups default to developer."""
    role = resolve_role(["SomeOtherGroup"])
    assert role == Role.DEVELOPER


def test_resolve_role_empty_groups():
    """Empty group list defaults to developer."""
    role = resolve_role([])
    assert role == Role.DEVELOPER


def test_developer_has_projects_read():
    assert has_permission(Role.DEVELOPER, "projects.read") is True


def test_developer_cannot_manage_users():
    assert has_permission(Role.DEVELOPER, "users.manage") is False


def test_faculty_has_users_manage():
    assert has_permission(Role.FACULTY, "users.manage") is True


def test_staff_has_deploys_rollback():
    assert has_permission(Role.STAFF, "deploys.rollback") is True


def test_check_permission_raises_on_deny():
    """check_permission should raise HTTPException for missing permission."""
    from fastapi import HTTPException
    import pytest

    with pytest.raises(HTTPException) as exc_info:
        check_permission(Role.DEVELOPER, "users.manage")
    assert exc_info.value.status_code == 403


def test_check_permission_allows_own_variant():
    """check_permission should pass if the '.own' variant exists."""
    # Developer has 'projects.update.own' but not 'projects.update'
    # check_permission("projects.update") should pass for developer (falls through to .own)
    check_permission(Role.DEVELOPER, "projects.update")  # should not raise

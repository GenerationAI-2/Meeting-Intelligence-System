"""Tests for permission enforcement across workspace roles.

Covers:
- Viewer: read only (no create/update/delete)
- Member: read + create + update own (no update others', no delete)
- Chair: full CRUD
- Org admin: bypasses all checks
- Archived workspace: blocks all writes
"""
import sys
import os
import pytest

# Add server/ to path so src package can be imported with relative imports intact
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import HTTPException
from src.workspace_context import WorkspaceContext, WorkspaceMembership
from src.permissions import check_permission


# --- Fixtures ---

def _make_membership(role="member", is_archived=False) -> WorkspaceMembership:
    return WorkspaceMembership(
        workspace_id=1,
        workspace_name="test",
        workspace_display_name="Test Workspace",
        db_name="test-db",
        role=role,
        is_default=True,
        is_archived=is_archived,
    )


def _make_ctx(role="member", is_org_admin=False, is_archived=False) -> WorkspaceContext:
    membership = _make_membership(role=role, is_archived=is_archived)
    return WorkspaceContext(
        user_email="user@example.com",
        is_org_admin=is_org_admin,
        memberships=[membership],
        active=membership,
    )


# --- Viewer Role Tests ---

class TestViewerPermissions:

    def test_viewer_can_read(self):
        ctx = _make_ctx(role="viewer")
        check_permission(ctx, "read")  # should not raise

    def test_viewer_cannot_create(self):
        ctx = _make_ctx(role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "create")
        assert exc_info.value.status_code == 403
        assert "Viewers cannot create" in str(exc_info.value.detail)

    def test_viewer_cannot_update(self):
        ctx = _make_ctx(role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "update")
        assert exc_info.value.status_code == 403
        assert "Viewers cannot edit" in str(exc_info.value.detail)

    def test_viewer_cannot_update_even_own(self):
        ctx = _make_ctx(role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "update", {"created_by": "user@example.com"})
        assert exc_info.value.status_code == 403

    def test_viewer_cannot_delete(self):
        ctx = _make_ctx(role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "delete")
        assert exc_info.value.status_code == 403
        assert "Only chairs can delete" in str(exc_info.value.detail)


# --- Member Role Tests ---

class TestMemberPermissions:

    def test_member_can_read(self):
        ctx = _make_ctx(role="member")
        check_permission(ctx, "read")

    def test_member_can_create(self):
        ctx = _make_ctx(role="member")
        check_permission(ctx, "create")

    def test_member_can_update_own(self):
        ctx = _make_ctx(role="member")
        check_permission(ctx, "update", {"created_by": "user@example.com"})

    def test_member_cannot_update_others(self):
        ctx = _make_ctx(role="member")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "update", {"created_by": "other@example.com"})
        assert exc_info.value.status_code == 403
        assert "Members can only edit their own" in str(exc_info.value.detail)

    def test_member_can_update_without_entity(self):
        """When entity is None, member update is allowed (e.g. create-like ops)."""
        ctx = _make_ctx(role="member")
        check_permission(ctx, "update")  # no entity = no ownership check

    def test_member_cannot_delete(self):
        ctx = _make_ctx(role="member")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "delete")
        assert exc_info.value.status_code == 403

    def test_member_cannot_manage_members(self):
        ctx = _make_ctx(role="member")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "manage_members")
        assert exc_info.value.status_code == 403


# --- Chair Role Tests ---

class TestChairPermissions:

    def test_chair_can_read(self):
        ctx = _make_ctx(role="chair")
        check_permission(ctx, "read")

    def test_chair_can_create(self):
        ctx = _make_ctx(role="chair")
        check_permission(ctx, "create")

    def test_chair_can_update_any(self):
        ctx = _make_ctx(role="chair")
        check_permission(ctx, "update", {"created_by": "other@example.com"})

    def test_chair_can_delete(self):
        ctx = _make_ctx(role="chair")
        check_permission(ctx, "delete")

    def test_chair_can_manage_members(self):
        ctx = _make_ctx(role="chair")
        check_permission(ctx, "manage_members")

    def test_chair_cannot_manage_workspace(self):
        ctx = _make_ctx(role="chair")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "manage_workspace")
        assert exc_info.value.status_code == 403


# --- Org Admin Tests ---

class TestOrgAdminPermissions:

    def test_org_admin_can_read(self):
        ctx = _make_ctx(role="viewer", is_org_admin=True)
        check_permission(ctx, "read")

    def test_org_admin_can_create(self):
        ctx = _make_ctx(role="viewer", is_org_admin=True)
        check_permission(ctx, "create")

    def test_org_admin_can_update_others(self):
        ctx = _make_ctx(role="viewer", is_org_admin=True)
        check_permission(ctx, "update", {"created_by": "other@example.com"})

    def test_org_admin_can_delete(self):
        ctx = _make_ctx(role="viewer", is_org_admin=True)
        check_permission(ctx, "delete")

    def test_org_admin_can_manage_members(self):
        ctx = _make_ctx(role="viewer", is_org_admin=True)
        check_permission(ctx, "manage_members")

    def test_org_admin_can_manage_workspace(self):
        ctx = _make_ctx(role="viewer", is_org_admin=True)
        check_permission(ctx, "manage_workspace")


# --- Archived Workspace Tests ---

class TestArchivedWorkspace:

    def test_archived_allows_read(self):
        ctx = _make_ctx(role="chair", is_archived=True)
        check_permission(ctx, "read")

    def test_archived_blocks_create(self):
        ctx = _make_ctx(role="chair", is_archived=True)
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "create")
        assert exc_info.value.status_code == 403
        assert "archived" in str(exc_info.value.detail).lower()

    def test_archived_blocks_update(self):
        ctx = _make_ctx(role="chair", is_archived=True)
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "update")
        assert exc_info.value.status_code == 403

    def test_archived_blocks_delete(self):
        ctx = _make_ctx(role="chair", is_archived=True)
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "delete")
        assert exc_info.value.status_code == 403

    def test_archived_org_admin_bypasses(self):
        """Org admin can write even in archived workspace."""
        ctx = _make_ctx(role="chair", is_org_admin=True, is_archived=True)
        check_permission(ctx, "create")
        check_permission(ctx, "update")
        check_permission(ctx, "delete")


# --- WorkspaceContext Helper Method Tests ---

class TestWorkspaceContextHelpers:

    def test_can_write_member(self):
        ctx = _make_ctx(role="member")
        assert ctx.can_write() is True

    def test_can_write_viewer(self):
        ctx = _make_ctx(role="viewer")
        assert ctx.can_write() is False

    def test_can_write_archived(self):
        ctx = _make_ctx(role="chair", is_archived=True)
        assert ctx.can_write() is False

    def test_can_write_org_admin_archived(self):
        ctx = _make_ctx(role="viewer", is_org_admin=True, is_archived=True)
        assert ctx.can_write() is True

    def test_is_chair_or_admin_chair(self):
        ctx = _make_ctx(role="chair")
        assert ctx.is_chair_or_admin() is True

    def test_is_chair_or_admin_member(self):
        ctx = _make_ctx(role="member")
        assert ctx.is_chair_or_admin() is False

    def test_is_chair_or_admin_org_admin(self):
        ctx = _make_ctx(role="viewer", is_org_admin=True)
        assert ctx.is_chair_or_admin() is True

    def test_role_shortcut(self):
        ctx = _make_ctx(role="member")
        assert ctx.role == "member"

    def test_db_name_shortcut(self):
        ctx = _make_ctx(role="member")
        assert ctx.db_name == "test-db"


# --- make_legacy_context Tests ---

class TestMakeLegacyContext:

    def test_legacy_context_is_org_admin(self):
        from src.workspace_context import make_legacy_context
        # Patch settings to avoid env var dependency
        os.environ.setdefault("AZURE_SQL_DATABASE", "test-db")
        ctx = make_legacy_context("test@example.com")
        assert ctx.is_org_admin is True

    def test_legacy_context_has_membership(self):
        from src.workspace_context import make_legacy_context
        os.environ.setdefault("AZURE_SQL_DATABASE", "test-db")
        ctx = make_legacy_context("test@example.com")
        assert len(ctx.memberships) == 1
        assert ctx.active.workspace_name == "default"
        assert ctx.active.role == "chair"

    def test_legacy_context_can_write(self):
        from src.workspace_context import make_legacy_context
        os.environ.setdefault("AZURE_SQL_DATABASE", "test-db")
        ctx = make_legacy_context("test@example.com")
        assert ctx.can_write() is True

    def test_legacy_context_all_permissions_pass(self):
        from src.workspace_context import make_legacy_context
        os.environ.setdefault("AZURE_SQL_DATABASE", "test-db")
        ctx = make_legacy_context("test@example.com")
        # All operations should pass without raising
        check_permission(ctx, "read")
        check_permission(ctx, "create")
        check_permission(ctx, "update", {"created_by": "other@example.com"})
        check_permission(ctx, "delete")
        check_permission(ctx, "manage_workspace")

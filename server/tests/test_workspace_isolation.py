"""Tests for workspace isolation — verifying that workspace context
correctly scopes data access and prevents cross-workspace leaks.

Covers:
- User A (ws_a only) can access ws_a data
- User A cannot access ws_b data (403)
- User B (ws_b only) gets ws_b data
- User C (both) can switch between workspaces
- Correct workspace DB name flows through context
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from fastapi import HTTPException
from src.workspace_context import WorkspaceContext, WorkspaceMembership
from src.permissions import check_permission
from src.dependencies import _resolve_active_workspace


# --- Helpers ---

def _ws(workspace_id, name, role="member", is_default=False, is_archived=False):
    return WorkspaceMembership(
        workspace_id=workspace_id,
        workspace_name=name,
        workspace_display_name=name.title(),
        db_name=f"mi-{name}",
        role=role,
        is_default=is_default,
        is_archived=is_archived,
    )


def _make_user_a_ctx():
    """User A: member of ws_a only."""
    ws_a = _ws(1, "alpha", role="member", is_default=True)
    return WorkspaceContext(
        user_email="user_a@example.com",
        is_org_admin=False,
        memberships=[ws_a],
        active=ws_a,
    )


def _make_user_b_ctx():
    """User B: member of ws_b only."""
    ws_b = _ws(2, "bravo", role="member", is_default=True)
    return WorkspaceContext(
        user_email="user_b@example.com",
        is_org_admin=False,
        memberships=[ws_b],
        active=ws_b,
    )


def _make_user_c_memberships():
    """User C: member of both ws_a and ws_b."""
    ws_a = _ws(1, "alpha", role="member")
    ws_b = _ws(2, "bravo", role="chair", is_default=True)
    return [ws_a, ws_b]


def _make_user_c_ctx(active_ws_name=None):
    """User C: member of both, active workspace resolved by name."""
    memberships = _make_user_c_memberships()
    active = _resolve_active_workspace(memberships, active_ws_name, None)
    return WorkspaceContext(
        user_email="user_c@example.com",
        is_org_admin=False,
        memberships=memberships,
        active=active,
    )


# --- User A: Single Workspace Access ---

class TestUserASingleWorkspace:

    def test_user_a_context_points_to_ws_a(self):
        ctx = _make_user_a_ctx()
        assert ctx.db_name == "mi-alpha"
        assert ctx.active.workspace_name == "alpha"

    def test_user_a_can_read(self):
        ctx = _make_user_a_ctx()
        check_permission(ctx, "read")  # should not raise

    def test_user_a_can_create(self):
        ctx = _make_user_a_ctx()
        check_permission(ctx, "create")

    def test_user_a_cannot_access_ws_b(self):
        """User A requesting ws_b should get 403."""
        ws_a = _ws(1, "alpha", role="member", is_default=True)
        with pytest.raises(HTTPException) as exc_info:
            _resolve_active_workspace([ws_a], "bravo", None)
        assert exc_info.value.status_code == 403
        assert "Not a member" in str(exc_info.value.detail)

    def test_user_a_cannot_access_ws_b_by_id(self):
        """User A requesting ws_b by ID should get 403."""
        ws_a = _ws(1, "alpha", role="member", is_default=True)
        with pytest.raises(HTTPException) as exc_info:
            _resolve_active_workspace([ws_a], "2", None)
        assert exc_info.value.status_code == 403


# --- User B: Separate Workspace ---

class TestUserBSeparateWorkspace:

    def test_user_b_context_points_to_ws_b(self):
        ctx = _make_user_b_ctx()
        assert ctx.db_name == "mi-bravo"
        assert ctx.active.workspace_name == "bravo"

    def test_user_b_can_read(self):
        ctx = _make_user_b_ctx()
        check_permission(ctx, "read")

    def test_user_b_cannot_access_ws_a(self):
        ws_b = _ws(2, "bravo", role="member", is_default=True)
        with pytest.raises(HTTPException) as exc_info:
            _resolve_active_workspace([ws_b], "alpha", None)
        assert exc_info.value.status_code == 403


# --- User C: Multi-Workspace Access ---

class TestUserCMultiWorkspace:

    def test_user_c_default_workspace(self):
        """Without explicit request, user C lands on org default (bravo, is_default=True)."""
        ctx = _make_user_c_ctx()
        assert ctx.active.workspace_name == "bravo"
        assert ctx.db_name == "mi-bravo"

    def test_user_c_switch_to_alpha(self):
        ctx = _make_user_c_ctx(active_ws_name="alpha")
        assert ctx.active.workspace_name == "alpha"
        assert ctx.db_name == "mi-alpha"

    def test_user_c_switch_to_bravo(self):
        ctx = _make_user_c_ctx(active_ws_name="bravo")
        assert ctx.active.workspace_name == "bravo"
        assert ctx.db_name == "mi-bravo"

    def test_user_c_has_both_memberships(self):
        ctx = _make_user_c_ctx()
        names = [m.workspace_name for m in ctx.memberships]
        assert "alpha" in names
        assert "bravo" in names

    def test_user_c_role_varies_by_workspace(self):
        """User C is member in alpha, chair in bravo."""
        ctx_alpha = _make_user_c_ctx(active_ws_name="alpha")
        ctx_bravo = _make_user_c_ctx(active_ws_name="bravo")
        assert ctx_alpha.role == "member"
        assert ctx_bravo.role == "chair"

    def test_user_c_permissions_change_with_workspace(self):
        """Chair in bravo can delete; member in alpha cannot."""
        ctx_alpha = _make_user_c_ctx(active_ws_name="alpha")
        ctx_bravo = _make_user_c_ctx(active_ws_name="bravo")

        with pytest.raises(HTTPException):
            check_permission(ctx_alpha, "delete")

        check_permission(ctx_bravo, "delete")  # chair can delete

    def test_user_c_cannot_access_unknown_workspace(self):
        memberships = _make_user_c_memberships()
        with pytest.raises(HTTPException) as exc_info:
            _resolve_active_workspace(memberships, "charlie", None)
        assert exc_info.value.status_code == 403


# --- Cross-Workspace Data Isolation ---

class TestCrossWorkspaceIsolation:
    """Verify that workspace context correctly isolates database access."""

    def test_different_users_get_different_db_names(self):
        ctx_a = _make_user_a_ctx()
        ctx_b = _make_user_b_ctx()
        assert ctx_a.db_name != ctx_b.db_name
        assert ctx_a.db_name == "mi-alpha"
        assert ctx_b.db_name == "mi-bravo"

    def test_switching_workspace_changes_db_name(self):
        ctx1 = _make_user_c_ctx(active_ws_name="alpha")
        ctx2 = _make_user_c_ctx(active_ws_name="bravo")
        assert ctx1.db_name == "mi-alpha"
        assert ctx2.db_name == "mi-bravo"

    def test_context_is_immutable(self):
        """WorkspaceContext is frozen — cannot be mutated after creation."""
        ctx = _make_user_a_ctx()
        with pytest.raises(AttributeError):
            ctx.user_email = "hacker@evil.com"
        with pytest.raises(AttributeError):
            ctx.active = _ws(99, "hacked")

    def test_membership_is_immutable(self):
        """WorkspaceMembership is frozen — cannot be mutated."""
        ws = _ws(1, "alpha")
        with pytest.raises(AttributeError):
            ws.db_name = "hacked-db"

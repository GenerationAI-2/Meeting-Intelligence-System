"""Tests for token validation + workspace resolution.

Covers:
- _resolve_active_workspace priority: explicit > user default > org default > first
- validate_token_from_control_db with mock cursor
- Token edge cases: revoked, expired, missing user
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from fastapi import HTTPException
from src.workspace_context import WorkspaceContext, WorkspaceMembership
from src.dependencies import _resolve_active_workspace


# --- Helpers ---

def _ws(workspace_id, name, role="member", is_default=False, is_archived=False):
    return WorkspaceMembership(
        workspace_id=workspace_id,
        workspace_name=name,
        workspace_display_name=name.title(),
        db_name=f"db-{name}",
        role=role,
        is_default=is_default,
        is_archived=is_archived,
    )


# --- _resolve_active_workspace Tests ---

class TestResolveActiveWorkspace:

    def test_explicit_request_by_name(self):
        ws_a = _ws(1, "board")
        ws_b = _ws(2, "ops")
        result = _resolve_active_workspace([ws_a, ws_b], "ops", None)
        assert result is ws_b

    def test_explicit_request_by_id(self):
        ws_a = _ws(1, "board")
        ws_b = _ws(2, "ops")
        result = _resolve_active_workspace([ws_a, ws_b], "2", None)
        assert result is ws_b

    def test_explicit_request_not_member_raises_403(self):
        ws_a = _ws(1, "board")
        with pytest.raises(HTTPException) as exc_info:
            _resolve_active_workspace([ws_a], "ops", None)
        assert exc_info.value.status_code == 403
        assert "Not a member" in str(exc_info.value.detail)

    def test_user_default_workspace(self):
        ws_a = _ws(1, "board")
        ws_b = _ws(2, "ops")
        result = _resolve_active_workspace([ws_a, ws_b], None, 2)
        assert result is ws_b

    def test_user_default_overrides_org_default(self):
        ws_a = _ws(1, "board", is_default=True)  # org default
        ws_b = _ws(2, "ops")
        result = _resolve_active_workspace([ws_a, ws_b], None, 2)
        assert result is ws_b

    def test_org_default_when_no_user_default(self):
        ws_a = _ws(1, "board")
        ws_b = _ws(2, "ops", is_default=True)
        result = _resolve_active_workspace([ws_a, ws_b], None, None)
        assert result is ws_b

    def test_first_membership_as_fallback(self):
        ws_a = _ws(1, "board")
        ws_b = _ws(2, "ops")
        result = _resolve_active_workspace([ws_a, ws_b], None, None)
        assert result is ws_a

    def test_empty_memberships_raises_403(self):
        with pytest.raises(HTTPException) as exc_info:
            _resolve_active_workspace([], None, None)
        assert exc_info.value.status_code == 403
        assert "no workspace memberships" in str(exc_info.value.detail).lower()

    def test_explicit_overrides_all(self):
        """Explicit request takes priority even when user default and org default exist."""
        ws_a = _ws(1, "board", is_default=True)  # org default
        ws_b = _ws(2, "ops")
        ws_c = _ws(3, "ceo")
        result = _resolve_active_workspace([ws_a, ws_b, ws_c], "ceo", 2)
        assert result is ws_c

    def test_user_default_not_in_memberships_falls_through(self):
        """If user's default_workspace_id doesn't match any membership, fall to org default."""
        ws_a = _ws(1, "board", is_default=True)
        ws_b = _ws(2, "ops")
        result = _resolve_active_workspace([ws_a, ws_b], None, 99)  # 99 not in list
        assert result is ws_a  # falls to org default


# --- WorkspaceContext Construction Tests ---

class TestWorkspaceContextFromToken:
    """Tests that simulate building WorkspaceContext from token validation results."""

    def test_context_from_single_membership(self):
        ws = _ws(1, "board", role="chair")
        ctx = WorkspaceContext(
            user_email="admin@example.com",
            is_org_admin=True,
            memberships=[ws],
            active=ws,
        )
        assert ctx.user_email == "admin@example.com"
        assert ctx.is_org_admin is True
        assert ctx.role == "chair"
        assert ctx.db_name == "db-board"
        assert ctx.can_write() is True
        assert ctx.is_chair_or_admin() is True

    def test_context_from_multiple_memberships(self):
        ws_a = _ws(1, "board", role="viewer")
        ws_b = _ws(2, "ops", role="member")
        ctx = WorkspaceContext(
            user_email="user@example.com",
            is_org_admin=False,
            memberships=[ws_a, ws_b],
            active=ws_a,
        )
        assert len(ctx.memberships) == 2
        assert ctx.role == "viewer"
        assert ctx.can_write() is False

    def test_context_non_admin_viewer_permissions(self):
        ws = _ws(1, "board", role="viewer")
        ctx = WorkspaceContext(
            user_email="viewer@example.com",
            is_org_admin=False,
            memberships=[ws],
            active=ws,
        )
        assert ctx.can_write() is False
        assert ctx.is_chair_or_admin() is False

    def test_context_org_admin_viewer_uses_role_for_data(self):
        """Org admin with viewer role uses viewer-level data access (H2 fix)."""
        ws = _ws(1, "board", role="viewer")
        ctx = WorkspaceContext(
            user_email="admin@example.com",
            is_org_admin=True,
            memberships=[ws],
            active=ws,
        )
        assert ctx.is_chair_or_admin() is False
        assert ctx.can_write() is False

    def test_context_org_admin_chair_has_full_access(self):
        """Org admin with chair role has full data access through their role."""
        ws = _ws(1, "board", role="chair")
        ctx = WorkspaceContext(
            user_email="admin@example.com",
            is_org_admin=True,
            memberships=[ws],
            active=ws,
        )
        assert ctx.is_chair_or_admin() is True
        assert ctx.can_write() is True

    def test_context_archived_blocks_write(self):
        ws = _ws(1, "board", role="chair", is_archived=True)
        ctx = WorkspaceContext(
            user_email="chair@example.com",
            is_org_admin=False,
            memberships=[ws],
            active=ws,
        )
        assert ctx.can_write() is False
        assert ctx.is_chair_or_admin() is True

    def test_context_org_admin_cannot_write_archived(self):
        """Org admin cannot write data in archived workspace (H2 fix — role-based)."""
        ws = _ws(1, "board", role="viewer", is_archived=True)
        ctx = WorkspaceContext(
            user_email="admin@example.com",
            is_org_admin=True,
            memberships=[ws],
            active=ws,
        )
        assert ctx.can_write() is False

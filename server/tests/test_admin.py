"""Tests for admin API — workspace CRUD and member management.

Tests focus on:
- Permission enforcement (org admin, chair, member, viewer)
- Pydantic validation (slug format, reserved names, role values)
- Business logic (last-chair protection, duplicate detection)
- Helper functions (_derive_db_name, _check_member_permission)

These are unit tests using constructed WorkspaceContext objects.
Integration tests with actual DB are out of scope for W3.
"""
import sys
import os
import re

import pytest

# Add server/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import HTTPException
from pydantic import ValidationError
from src.workspace_context import WorkspaceContext, WorkspaceMembership
from src.permissions import check_permission
from src.admin import (
    WorkspaceCreate,
    WorkspaceArchive,
    MemberAdd,
    MemberRoleUpdate,
    _derive_db_name,
    _check_member_permission,
    SLUG_PATTERN,
    RESERVED_NAMES,
)


# --- Fixtures ---

def _make_membership(workspace_id=1, role="chair", workspace_name="test") -> WorkspaceMembership:
    return WorkspaceMembership(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_display_name="Test Workspace",
        db_name="test-db",
        role=role,
        is_default=True,
        is_archived=False,
    )


def _make_ctx(role="chair", is_org_admin=False, workspace_id=1) -> WorkspaceContext:
    membership = _make_membership(role=role, workspace_id=workspace_id)
    return WorkspaceContext(
        user_email="user@example.com",
        is_org_admin=is_org_admin,
        memberships=[membership],
        active=membership,
    )


# --- Pydantic Validation Tests ---

class TestWorkspaceCreateValidation:

    def test_valid_slug(self):
        ws = WorkspaceCreate(name="board", display_name="Board")
        assert ws.name == "board"

    def test_slug_with_hyphens_and_numbers(self):
        ws = WorkspaceCreate(name="ceo-office-2", display_name="CEO Office 2")
        assert ws.name == "ceo-office-2"

    def test_invalid_slug_uppercase(self):
        with pytest.raises(ValidationError) as exc_info:
            WorkspaceCreate(name="Board", display_name="Board")
        assert "URL-safe slug" in str(exc_info.value)

    def test_invalid_slug_spaces(self):
        with pytest.raises(ValidationError):
            WorkspaceCreate(name="my board", display_name="Board")

    def test_invalid_slug_special_chars(self):
        with pytest.raises(ValidationError):
            WorkspaceCreate(name="board!", display_name="Board")

    def test_slug_too_short(self):
        with pytest.raises(ValidationError):
            WorkspaceCreate(name="a", display_name="A")

    def test_reserved_name_admin(self):
        with pytest.raises(ValidationError) as exc_info:
            WorkspaceCreate(name="admin", display_name="Admin")
        assert "reserved" in str(exc_info.value)

    def test_reserved_name_api(self):
        with pytest.raises(ValidationError):
            WorkspaceCreate(name="api", display_name="API")

    def test_reserved_name_control(self):
        with pytest.raises(ValidationError):
            WorkspaceCreate(name="control", display_name="Control")

    def test_display_name_required(self):
        with pytest.raises(ValidationError):
            WorkspaceCreate(name="board", display_name="")


class TestMemberAddValidation:

    def test_valid_member(self):
        m = MemberAdd(email="user@example.com", display_name="User", role="member")
        assert m.email == "user@example.com"
        assert m.role == "member"

    def test_email_normalized_lowercase(self):
        m = MemberAdd(email="User@Example.COM", role="viewer")
        assert m.email == "user@example.com"

    def test_email_trimmed(self):
        m = MemberAdd(email="  user@example.com  ", role="chair")
        assert m.email == "user@example.com"

    def test_invalid_email_no_at(self):
        with pytest.raises(ValidationError):
            MemberAdd(email="userexample.com", role="member")

    def test_invalid_role(self):
        with pytest.raises(ValidationError) as exc_info:
            MemberAdd(email="user@example.com", role="admin")
        assert "role must be one of" in str(exc_info.value)

    def test_valid_roles(self):
        for role in ("viewer", "member", "chair"):
            m = MemberAdd(email="user@example.com", role=role)
            assert m.role == role


class TestMemberRoleUpdateValidation:

    def test_valid_role(self):
        u = MemberRoleUpdate(role="chair")
        assert u.role == "chair"

    def test_invalid_role(self):
        with pytest.raises(ValidationError):
            MemberRoleUpdate(role="admin")


# --- Permission Tests ---

class TestWorkspaceAdminPermissions:

    def test_org_admin_can_manage_workspace(self):
        ctx = _make_ctx(is_org_admin=True)
        check_permission(ctx, "manage_workspace")  # should not raise

    def test_chair_cannot_manage_workspace(self):
        ctx = _make_ctx(role="chair")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "manage_workspace")
        assert exc_info.value.status_code == 403

    def test_member_cannot_manage_workspace(self):
        ctx = _make_ctx(role="member")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "manage_workspace")
        assert exc_info.value.status_code == 403

    def test_viewer_cannot_manage_workspace(self):
        ctx = _make_ctx(role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "manage_workspace")
        assert exc_info.value.status_code == 403


class TestMemberManagementPermissions:

    def test_org_admin_can_manage_any_workspace_members(self):
        ctx = _make_ctx(is_org_admin=True, workspace_id=1)
        _check_member_permission(ctx, workspace_id=99)  # different workspace

    def test_chair_can_manage_own_workspace_members(self):
        ctx = _make_ctx(role="chair", workspace_id=1)
        _check_member_permission(ctx, workspace_id=1)  # same workspace

    def test_chair_cannot_manage_other_workspace_members(self):
        ctx = _make_ctx(role="chair", workspace_id=1)
        with pytest.raises(HTTPException) as exc_info:
            _check_member_permission(ctx, workspace_id=99)  # different workspace
        assert exc_info.value.status_code == 403

    def test_member_cannot_manage_members(self):
        ctx = _make_ctx(role="member", workspace_id=1)
        with pytest.raises(HTTPException) as exc_info:
            _check_member_permission(ctx, workspace_id=1)
        assert exc_info.value.status_code == 403

    def test_viewer_cannot_manage_members(self):
        ctx = _make_ctx(role="viewer", workspace_id=1)
        with pytest.raises(HTTPException) as exc_info:
            _check_member_permission(ctx, workspace_id=1)
        assert exc_info.value.status_code == 403


# --- Helper Function Tests ---

class TestDeriveDbName:

    def test_standard_convention(self):
        """marshall-mi-control → marshall-mi-{slug}"""
        from unittest.mock import patch, MagicMock
        mock_settings = MagicMock()
        mock_settings.control_db_name = "marshall-mi-control"
        with patch("src.admin.get_settings", return_value=mock_settings):
            assert _derive_db_name("board") == "marshall-mi-board"

    def test_hyphenated_slug(self):
        from unittest.mock import patch, MagicMock
        mock_settings = MagicMock()
        mock_settings.control_db_name = "acme-mi-control"
        with patch("src.admin.get_settings", return_value=mock_settings):
            assert _derive_db_name("ceo-office") == "acme-mi-ceo-office"

    def test_fallback_convention(self):
        """Non-standard control DB name uses rsplit fallback."""
        from unittest.mock import patch, MagicMock
        mock_settings = MagicMock()
        mock_settings.control_db_name = "mydb-ctrl"
        with patch("src.admin.get_settings", return_value=mock_settings):
            assert _derive_db_name("board") == "mydb-board"


class TestSlugPattern:

    def test_valid_slugs(self):
        valid = ["ab", "board", "ceo-office", "ops-2", "a1", "test-workspace-name"]
        for slug in valid:
            assert SLUG_PATTERN.match(slug), f"Expected '{slug}' to be valid"

    def test_invalid_slugs(self):
        invalid = [
            "a",           # too short
            "-board",      # starts with hyphen
            "board-",      # ends with hyphen
            "Board",       # uppercase
            "my board",    # space
            "board!",      # special char
            "",            # empty
        ]
        for slug in invalid:
            assert not SLUG_PATTERN.match(slug), f"Expected '{slug}' to be invalid"

    def test_all_reserved_names(self):
        expected = {"admin", "api", "mcp", "sse", "health", "oauth",
                    "default", "system", "control", "master"}
        assert RESERVED_NAMES == expected

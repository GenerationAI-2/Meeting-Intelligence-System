"""Tests for admin token management — permission enforcement and validation.

Covers:
- Permission checks: only org_admin can manage tokens (manage_workspace)
- AdminTokenCreate Pydantic validation (name length, expiry bounds)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.workspace_context import WorkspaceContext, WorkspaceMembership
from src.permissions import check_permission
from src.admin import AdminTokenCreate


# --- Helpers ---


def _make_membership(workspace_id=1, role="chair", workspace_name="test"):
    return WorkspaceMembership(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_display_name="Test Workspace",
        db_name="test-db",
        role=role,
        is_default=True,
        is_archived=False,
    )


def _make_ctx(role="chair", is_org_admin=False):
    membership = _make_membership(role=role)
    return WorkspaceContext(
        user_email="admin@example.com",
        is_org_admin=is_org_admin,
        memberships=[membership],
        active=membership,
    )


# --- Permission Tests ---


class TestAdminTokenPermissions:
    """Only org_admin should be able to manage tokens via admin API."""

    def test_org_admin_can_manage_tokens(self):
        ctx = _make_ctx(is_org_admin=True)
        check_permission(ctx, "manage_workspace")  # should not raise

    def test_chair_cannot_manage_tokens(self):
        ctx = _make_ctx(role="chair")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "manage_workspace")
        assert exc_info.value.status_code == 403

    def test_member_cannot_manage_tokens(self):
        ctx = _make_ctx(role="member")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "manage_workspace")
        assert exc_info.value.status_code == 403

    def test_viewer_cannot_manage_tokens(self):
        ctx = _make_ctx(role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            check_permission(ctx, "manage_workspace")
        assert exc_info.value.status_code == 403


# --- Pydantic Validation Tests ---


class TestAdminTokenCreateValidation:
    """AdminTokenCreate model validation."""

    def test_valid_token_create(self):
        t = AdminTokenCreate(client_name="Claude Desktop", expires_days=90)
        assert t.client_name == "Claude Desktop"
        assert t.expires_days == 90

    def test_no_expiry_is_valid(self):
        t = AdminTokenCreate(client_name="Claude Desktop")
        assert t.expires_days is None

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            AdminTokenCreate(client_name="")

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError):
            AdminTokenCreate(client_name="x" * 256)

    def test_max_length_name_accepted(self):
        t = AdminTokenCreate(client_name="x" * 255)
        assert len(t.client_name) == 255

    def test_zero_expiry_rejected(self):
        with pytest.raises(ValidationError):
            AdminTokenCreate(client_name="test", expires_days=0)

    def test_negative_expiry_rejected(self):
        with pytest.raises(ValidationError):
            AdminTokenCreate(client_name="test", expires_days=-1)

    def test_expiry_over_365_rejected(self):
        with pytest.raises(ValidationError):
            AdminTokenCreate(client_name="test", expires_days=400)

    def test_max_expiry_accepted(self):
        t = AdminTokenCreate(client_name="test", expires_days=365)
        assert t.expires_days == 365

    def test_one_day_expiry_accepted(self):
        t = AdminTokenCreate(client_name="test", expires_days=1)
        assert t.expires_days == 1

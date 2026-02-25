"""Tests for audit logging utility.

Covers:
- Audit log insertion with correct parameters
- Detail truncation to 500 chars
- Exception swallowing (audit failures must not break operations)
- NULL workspace_id for legacy contexts
"""
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# Add server/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.workspace_context import WorkspaceContext, WorkspaceMembership
from src.audit import log_audit


# --- Fixtures ---

def _make_membership(workspace_id=1, workspace_name="test") -> WorkspaceMembership:
    return WorkspaceMembership(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        workspace_display_name="Test Workspace",
        db_name="test-db",
        role="chair",
        is_default=True,
        is_archived=False,
    )


def _make_ctx(workspace_id=1, workspace_name="test") -> WorkspaceContext:
    membership = _make_membership(workspace_id=workspace_id, workspace_name=workspace_name)
    return WorkspaceContext(
        user_email="admin@example.com",
        is_org_admin=True,
        memberships=[membership],
        active=membership,
    )


# --- Tests ---

class TestLogAudit:

    def test_inserts_row_with_correct_params(self):
        cursor = MagicMock()
        ctx = _make_ctx()

        log_audit(cursor, ctx, "create", "workspace", entity_id=42, detail="Created workspace")

        cursor.execute.assert_called_once()
        call_args = cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "INSERT INTO audit_log" in sql
        assert params[0] == "admin@example.com"  # user_email
        assert params[1] == 1                      # workspace_id
        assert params[2] == "test"                 # workspace_name
        assert params[3] == "create"               # operation
        assert params[4] == "workspace"            # entity_type
        assert params[5] == 42                     # entity_id
        assert params[6] == "Created workspace"    # detail
        assert params[7] == "admin"                # auth_method (default)

    def test_truncates_detail_to_500_chars(self):
        cursor = MagicMock()
        ctx = _make_ctx()
        long_detail = "x" * 1000

        log_audit(cursor, ctx, "create", "meeting", detail=long_detail)

        params = cursor.execute.call_args[0][1]
        assert len(params[6]) == 500

    def test_null_detail_passes_through(self):
        cursor = MagicMock()
        ctx = _make_ctx()

        log_audit(cursor, ctx, "read", "meeting")

        params = cursor.execute.call_args[0][1]
        assert params[5] is None   # entity_id
        assert params[6] is None   # detail

    def test_swallows_exceptions(self):
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB connection lost")
        ctx = _make_ctx()

        # Should not raise
        log_audit(cursor, ctx, "create", "workspace", entity_id=1)

    def test_legacy_context_stores_null_workspace(self):
        """workspace_id=0 (legacy context) should be stored as NULL."""
        cursor = MagicMock()
        ctx = _make_ctx(workspace_id=0, workspace_name="default")

        log_audit(cursor, ctx, "read", "meeting")

        params = cursor.execute.call_args[0][1]
        assert params[1] is None   # workspace_id should be NULL
        assert params[2] is None   # workspace_name should be NULL

    def test_custom_auth_method(self):
        cursor = MagicMock()
        ctx = _make_ctx()

        log_audit(cursor, ctx, "create", "meeting", auth_method="mcp")

        params = cursor.execute.call_args[0][1]
        assert params[7] == "mcp"

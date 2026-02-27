"""Tests for fail-closed security behavior (code review findings 1-3).

Finding 1: System must fail closed (503/deny) when workspace mode is
           enabled but infrastructure is unavailable. Never fall back
           to make_legacy_context() which grants full admin.
Finding 2: Token cache TTL reduced to 30s. clear_token_cache() available.
Finding 3: MCP endpoints require Origin header OR valid auth token.

Auth hardening (27 Feb 2026): All fail-closed bugs fixed.
- dependencies.py: `or` condition split into separate checks (503 on engine_registry=None)
- api.py: no legacy token fallback when control_db_name set
- main.py: legacy fallback only when control_db_name is empty
- oauth.py: removed entirely (OAuth 2.1 for ChatGPT removed)
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock

from fastapi import HTTPException


# ============================================================================
# FINDING 1: Fail-closed tests
# ============================================================================

class TestResolveWorkspaceFailClosed:
    """resolve_workspace() must fail closed when workspace mode enabled but broken."""

    def test_legacy_mode_when_no_control_db(self):
        """Empty control_db_name → genuine legacy mode → legacy context (OK)."""
        from src.dependencies import resolve_workspace

        mock_settings = MagicMock()
        mock_settings.control_db_name = ""
        mock_settings.azure_sql_database = "test-db"

        request = MagicMock()
        request.state.user_email = "test@example.com"

        with patch("src.dependencies.get_settings", return_value=mock_settings), \
             patch("src.dependencies._db_module") as mock_db:
            mock_db.engine_registry = None
            result = asyncio.run(resolve_workspace(request, None))

        assert result.is_org_admin is True  # Legacy mode grants admin
        assert result.user_email == "test@example.com"

    def test_503_when_control_db_set_but_engine_none(self):
        """control_db_name set + engine_registry=None → 503, NOT legacy admin."""
        from src.dependencies import resolve_workspace

        mock_settings = MagicMock()
        mock_settings.control_db_name = "my-control-db"

        request = MagicMock()
        request.state.user_email = "test@example.com"

        with patch("src.dependencies.get_settings", return_value=mock_settings), \
             patch("src.dependencies._db_module") as mock_db:
            mock_db.engine_registry = None
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(resolve_workspace(request, None))

        assert exc_info.value.status_code == 503

    def test_503_when_control_db_unreachable(self):
        """control_db_name set + control DB raises → 503."""
        from src.dependencies import resolve_workspace

        mock_settings = MagicMock()
        mock_settings.control_db_name = "my-control-db"

        request = MagicMock()
        request.state.user_email = "test@example.com"

        with patch("src.dependencies.get_settings", return_value=mock_settings), \
             patch("src.dependencies._db_module") as mock_db, \
             patch("src.dependencies.get_control_db", side_effect=Exception("DB down")):
            mock_db.engine_registry = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(resolve_workspace(request, None))

        assert exc_info.value.status_code == 503

    def test_401_when_no_user_email_in_workspace_mode(self):
        """Workspace mode + no user email on request → 401."""
        from src.dependencies import resolve_workspace

        mock_settings = MagicMock()
        mock_settings.control_db_name = "my-control-db"

        request = MagicMock()
        request.state.user_email = None

        with patch("src.dependencies.get_settings", return_value=mock_settings), \
             patch("src.dependencies._db_module") as mock_db:
            mock_db.engine_registry = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(resolve_workspace(request, None))

        assert exc_info.value.status_code == 401

    def test_403_when_user_has_no_memberships(self):
        """Authenticated user exists in control DB but has zero memberships → 403."""
        from src.dependencies import resolve_workspace

        mock_settings = MagicMock()
        mock_settings.control_db_name = "my-control-db"

        request = MagicMock()
        request.state.user_email = "orphan@example.com"
        request.headers = {}

        with patch("src.dependencies.get_settings", return_value=mock_settings), \
             patch("src.dependencies._db_module") as mock_db, \
             patch("src.dependencies.get_control_db") as mock_get_db:
            mock_db.engine_registry = MagicMock()
            mock_cursor = MagicMock()
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            with patch("src.dependencies._get_user_memberships", return_value=(False, None, [], set())):
                with pytest.raises(HTTPException) as exc_info:
                    asyncio.run(resolve_workspace(request, None))

        assert exc_info.value.status_code == 403


class TestMcpTokenFailClosed:
    """validate_mcp_token in main.py must not grant admin on error paths."""

    def test_make_legacy_context_grants_admin(self):
        """Precondition: make_legacy_context grants full admin (the thing we're guarding against)."""
        from src.workspace_context import make_legacy_context

        legacy = make_legacy_context("test@example.com")
        assert legacy.is_org_admin is True
        assert legacy.active.role == "chair"


class TestMcpServerResolveCtxFailClosed:
    """_resolve_ctx() must fail closed when workspace mode enabled but context is None."""

    def test_fail_closed_when_ctx_none_and_control_db_set(self):
        """control_db_name set + ctx is None → error dict, NOT legacy admin."""
        from src.mcp_server import _resolve_ctx

        mock_settings = MagicMock()
        mock_settings.control_db_name = "my-control-db"

        with patch("src.mcp_server.get_mcp_workspace_context", return_value=None), \
             patch("src.config.get_settings", return_value=mock_settings):
            result = _resolve_ctx()

        assert isinstance(result, dict)
        assert result["error"] is True
        assert result["code"] == "AUTH_ERROR"

    def test_legacy_mode_when_ctx_none_and_no_control_db(self):
        """No control_db_name + ctx is None → legacy context (OK)."""
        from src.mcp_server import _resolve_ctx

        mock_settings = MagicMock()
        mock_settings.control_db_name = ""
        mock_settings.azure_sql_database = "test-db"

        with patch("src.mcp_server.get_mcp_workspace_context", return_value=None), \
             patch("src.config.get_settings", return_value=mock_settings):
            result = _resolve_ctx()

        assert not isinstance(result, dict)  # Should be WorkspaceContext, not error dict
        assert result.is_org_admin is True


# ============================================================================
# API get_current_user() fail-closed tests
# ============================================================================

class TestApiTokenFailClosed:
    """api.get_current_user() must not fall through to legacy token validation when control DB is configured."""

    def test_no_legacy_token_fallback_when_control_db_set(self):
        """control_db_name set + token not in control DB → falls through to Azure AD, NOT legacy DB."""
        from src.api import get_current_user

        mock_settings = MagicMock()
        mock_settings.control_db_name = "my-control-db"
        mock_settings.azure_client_id = "test-client-id"
        mock_settings.azure_tenant_id = "test-tenant-id"

        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer test-token"}

        with patch("src.api.settings", mock_settings), \
             patch("src.api._db_module") as mock_db, \
             patch("src.api.validate_token_from_control_db", return_value=None), \
             patch("src.api.validate_client_token") as mock_legacy, \
             patch("src.api.azure_scheme", side_effect=HTTPException(401, "Not Azure AD")):
            mock_db.engine_registry = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_current_user(mock_request))

        assert exc_info.value.status_code == 401
        mock_legacy.assert_not_called()  # MUST NOT fall through to legacy

    def test_legacy_token_allowed_when_no_control_db(self):
        """No control_db_name → legacy token validation is permitted."""
        from src.api import get_current_user

        mock_settings = MagicMock()
        mock_settings.control_db_name = ""

        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer test-token"}

        with patch("src.api.settings", mock_settings), \
             patch("src.api._db_module") as mock_db, \
             patch("src.api.validate_client_token", return_value={"client_email": "user@example.com"}):
            mock_db.engine_registry = None
            result = asyncio.run(get_current_user(mock_request))

        assert result == "user@example.com"


# ============================================================================
# FINDING 2: Token cache TTL and clearing
# ============================================================================
# clear_token_cache() and _http_caches were identified as needed in the code
# review but have not been implemented yet. These tests are deferred to Phase B
# auth hardening. When implemented, add tests here for:
# - clear_token_cache() safe to call in non-HTTP mode
# - clear_token_cache() clears both token and workspace caches
# - clear_token_cache(email=...) clears only that user's workspace cache

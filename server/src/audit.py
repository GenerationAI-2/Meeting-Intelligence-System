"""Meeting Intelligence — Audit Logging

Writes to the audit_log table in the control database.
Called from admin endpoints and (future) tool functions after successful operations.
"""

import pyodbc
from .workspace_context import WorkspaceContext
from .logging_config import get_logger

logger = get_logger(__name__)


def log_audit(
    cursor_control: pyodbc.Cursor,
    ctx: WorkspaceContext,
    operation: str,
    entity_type: str,
    entity_id: int = None,
    detail: str = None,
    auth_method: str = "admin",
) -> None:
    """Insert a row into audit_log in the control database.

    Parameters:
        cursor_control: Cursor connected to the control database
        ctx: The resolved WorkspaceContext for the current request
        operation: One of 'read', 'create', 'update', 'delete'
        entity_type: One of 'meeting', 'action', 'decision', 'workspace', 'member', 'token'
        entity_id: ID of the entity (None for list operations)
        detail: Optional free-text context (truncated to 500 chars)
        auth_method: One of 'mcp', 'web', 'oauth', 'admin'
    """
    try:
        # Legacy context uses workspace_id=0; store as NULL
        workspace_id = ctx.active.workspace_id if ctx.active.workspace_id != 0 else None
        workspace_name = ctx.active.workspace_name if workspace_id else None

        cursor_control.execute(
            """
            INSERT INTO audit_log
                (user_email, workspace_id, workspace_name, operation,
                 entity_type, entity_id, detail, auth_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ctx.user_email,
                workspace_id,
                workspace_name,
                operation,
                entity_type,
                entity_id,
                detail[:500] if detail else None,
                auth_method,
            ),
        )
    except Exception as e:
        # Audit failure must never break the main operation
        logger.error("Failed to write audit log: %s", e, exc_info=True)

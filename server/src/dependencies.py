"""Meeting Intelligence — FastAPI Dependency Chain

Provides Depends()-compatible functions for workspace-scoped database access.

Dependency chain:
  authenticate_and_store → resolve_workspace → get_workspace_db
"""

from fastapi import Depends, Header, HTTPException, Request
from typing import Optional, Generator
import pyodbc

from . import database as _db_module
from .database import get_db_for, get_control_db, _get_engine
from .workspace_context import WorkspaceContext, WorkspaceMembership, make_legacy_context
from .config import get_settings
from .logging_config import get_logger

logger = get_logger(__name__)


# --- Layer 1: Authenticate ---

async def authenticate_and_store(request: Request) -> str:
    """Run existing auth and store user email on request.state for resolve_workspace.

    Bridge pattern: avoids rewriting get_current_user (that is W3 scope).
    Lazy import to avoid circular dependency with api.py.
    """
    from .api import get_current_user
    user_email = await get_current_user(request)
    request.state.user_email = user_email
    return user_email


# --- Layer 2: Resolve workspace ---

def _get_user_memberships(
    cursor: pyodbc.Cursor, email: str
) -> tuple[bool, Optional[int], list[WorkspaceMembership]]:
    """Query control DB: user -> is_org_admin + default_workspace_id + workspace memberships.

    Returns (is_org_admin, default_workspace_id, [WorkspaceMembership, ...]).
    SQL joins users -> workspace_members -> workspaces.
    """
    cursor.execute(
        """
        SELECT u.is_org_admin, u.default_workspace_id
        FROM users u
        WHERE u.email = ?
        """,
        (email,)
    )
    user_row = cursor.fetchone()
    if not user_row:
        return (False, None, [])

    is_org_admin = bool(user_row[0])
    default_workspace_id = user_row[1]

    cursor.execute(
        """
        SELECT w.id, w.name, w.display_name, w.db_name, wm.role,
               w.is_default, w.is_archived
        FROM workspace_members wm
        JOIN workspaces w ON w.id = wm.workspace_id
        WHERE wm.user_id = (SELECT id FROM users WHERE email = ?)
          AND w.is_archived = 0
        ORDER BY w.is_default DESC, w.name
        """,
        (email,)
    )
    rows = cursor.fetchall()
    memberships = [
        WorkspaceMembership(
            workspace_id=row[0],
            workspace_name=row[1],
            workspace_display_name=row[2],
            db_name=row[3],
            role=row[4],
            is_default=bool(row[5]),
            is_archived=bool(row[6]),
        )
        for row in rows
    ]
    return (is_org_admin, default_workspace_id, memberships)


def _resolve_active_workspace(
    memberships: list[WorkspaceMembership],
    requested: Optional[str],
    default_workspace_id: Optional[int],
) -> WorkspaceMembership:
    """Pick the active workspace: explicit request > user default > org default > first."""
    if not memberships:
        raise HTTPException(403, "User has no workspace memberships")

    # Explicit request via header
    if requested:
        for m in memberships:
            if m.workspace_name == requested or str(m.workspace_id) == requested:
                return m
        raise HTTPException(403, f"Not a member of workspace '{requested}'")

    # User's default workspace
    if default_workspace_id:
        for m in memberships:
            if m.workspace_id == default_workspace_id:
                return m

    # Org default (is_default=True)
    for m in memberships:
        if m.is_default:
            return m

    # First membership
    return memberships[0]


async def resolve_workspace(
    request: Request,
    x_workspace_id: Optional[str] = Header(None, alias="X-Workspace-ID"),
) -> WorkspaceContext:
    """Full workspace resolution. Produces the immutable WorkspaceContext for this request."""
    settings = get_settings()

    # Legacy mode: no control database configured
    if not settings.control_db_name or not _db_module.engine_registry:
        user_email = getattr(request.state, 'user_email', 'system@generationai.co.nz')
        logger.warning("resolve_workspace: LEGACY MODE (control_db_name=%s, engine_registry=%s)",
                       settings.control_db_name, bool(_db_module.engine_registry))
        return make_legacy_context(user_email)

    # Workspace mode: query control DB for memberships
    user_email = getattr(request.state, 'user_email', None)
    if not user_email:
        raise HTTPException(401, "Authentication required")

    try:
        with get_control_db() as cursor:
            is_org_admin, default_ws_id, memberships = _get_user_memberships(cursor, user_email)
    except Exception as e:
        logger.error("resolve_workspace: control DB unavailable — failing closed: %s: %s",
                     type(e).__name__, e)
        raise HTTPException(503, "Service temporarily unavailable — please retry")

    if not memberships:
        raise HTTPException(403, "User has no workspace memberships")

    active = _resolve_active_workspace(memberships, x_workspace_id, default_ws_id)

    return WorkspaceContext(
        user_email=user_email,
        is_org_admin=is_org_admin,
        memberships=memberships,
        active=active,
    )


# --- Layer 3: Get workspace-scoped DB cursor ---

def get_workspace_db(
    ctx: WorkspaceContext = Depends(resolve_workspace),
) -> Generator[pyodbc.Cursor, None, None]:
    """Yield a pyodbc cursor connected to the active workspace database."""
    if _db_module.engine_registry:
        eng = _db_module.engine_registry.get_engine(ctx.db_name)
    else:
        eng = _get_engine()
    with get_db_for(eng) as cursor:
        yield cursor

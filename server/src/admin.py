"""Meeting Intelligence — Admin API

Workspace CRUD (Org Admin only) and Member management (Chair + Org Admin).
All endpoints query the CONTROL database, not workspace databases.
"""

import os
import re
import struct
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from .audit import log_audit
from .config import get_settings
from . import database as _db_module
from .database import get_control_db, get_db_for
from .dependencies import authenticate_and_store, resolve_workspace
from .logging_config import get_logger
from .permissions import check_permission
from .workspace_context import WorkspaceContext

logger = get_logger(__name__)

admin_router = APIRouter(tags=["admin"])


# ==========================================================================
# Pydantic Request Models
# ==========================================================================

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,98}[a-z0-9]$")

RESERVED_NAMES = frozenset({
    "admin", "api", "mcp", "sse", "health", "oauth",
    "default", "system", "control", "master",
})


class WorkspaceCreate(BaseModel):
    name: str = Field(
        ..., min_length=2, max_length=100,
        description="URL-safe slug: lowercase, hyphens, no spaces",
    )
    display_name: str = Field(
        ..., min_length=1, max_length=255,
        description="Human-readable name",
    )

    @field_validator("name")
    @classmethod
    def validate_slug(cls, v):
        if not SLUG_PATTERN.match(v):
            raise ValueError(
                "name must be a URL-safe slug: lowercase letters, numbers, hyphens. "
                "Must start and end with a letter or number. 2-100 characters."
            )
        if v in RESERVED_NAMES:
            raise ValueError(f"'{v}' is a reserved name")
        return v


class WorkspaceArchive(BaseModel):
    is_archived: bool = Field(..., description="True to archive, False to unarchive")


class MemberAdd(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    role: str = Field(..., description="One of: viewer, member, chair")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[1]:
            raise ValueError("Invalid email address")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        valid = {"viewer", "member", "chair"}
        if v not in valid:
            raise ValueError(f"role must be one of: {', '.join(sorted(valid))}")
        return v


class MemberRoleUpdate(BaseModel):
    role: str = Field(..., description="New role: viewer, member, or chair")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        valid = {"viewer", "member", "chair"}
        if v not in valid:
            raise ValueError(f"role must be one of: {', '.join(sorted(valid))}")
        return v


# ==========================================================================
# Internal helpers
# ==========================================================================

def _derive_db_name(workspace_slug: str) -> str:
    """Derive the Azure SQL database name from the control DB naming convention.

    Convention: control_db_name ends with '-control' → replace with '-{slug}'.
    E.g. 'marshall-mi-control' → 'marshall-mi-board'
    """
    settings = get_settings()
    control_db = settings.control_db_name
    if control_db.endswith("-control"):
        prefix = control_db[:-8]  # strip '-control'
    else:
        prefix = control_db.rsplit("-", 1)[0]
    return f"{prefix}-{workspace_slug}"


def _check_member_permission(ctx: WorkspaceContext, workspace_id: int) -> None:
    """Check that the user can manage members of the given workspace.

    Allowed: org admin, or chair of that specific workspace.
    """
    if ctx.is_org_admin:
        return
    is_chair = any(
        m.workspace_id == workspace_id and m.role == "chair"
        for m in ctx.memberships
    )
    if not is_chair:
        raise HTTPException(403, "Only org admins or workspace chairs can manage members")


def _get_azure_token_struct():
    """Get Azure AD token struct for raw pyodbc connections."""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token_bytes = credential.get_token(
        "https://database.windows.net/.default"
    ).token.encode("UTF-16-LE")
    return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)


def _create_workspace_database(sql_server: str, db_name: str) -> None:
    """Create a new SQL database on the Azure SQL Server.

    Connects to master database with autocommit (DDL requires it).
    """
    token_struct = _get_azure_token_struct()
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={sql_server};"
        f"DATABASE=master;"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    SQL_COPT_SS_ACCESS_TOKEN = 1256
    conn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
    conn.autocommit = True
    try:
        cursor = conn.cursor()
        # Basic tier, 2GB — matches existing workspace databases
        cursor.execute(
            f"CREATE DATABASE [{db_name}] "
            f"(EDITION = 'Basic', SERVICE_OBJECTIVE = 'Basic', MAXSIZE = 2 GB)"
        )
        logger.info("Created database '%s' on server '%s'", db_name, sql_server)
    finally:
        conn.close()


def _run_workspace_schema(db_name: str) -> None:
    """Run the workspace schema SQL against a newly created database.

    Reads schema.sql and executes each statement. Idempotent — ignores
    'already exists' errors.
    """
    # Look for schema.sql relative to this file: server/src/admin.py → ../../schema.sql
    schema_path = os.path.join(os.path.dirname(__file__), "..", "..", "schema.sql")
    # In Docker container the file may be at /app/schema.sql
    if not os.path.exists(schema_path):
        schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"schema.sql not found (tried relative paths from {__file__})")

    with open(schema_path, "r") as f:
        schema_sql = f.read()

    eng = _db_module.engine_registry.get_engine(db_name)
    with get_db_for(eng) as cursor:
        for raw_statement in schema_sql.split(";"):
            # Strip SQL comment lines before checking if the statement is empty.
            # Without this, a statement block like "-- comment\nCREATE TABLE ..."
            # would be skipped entirely because it starts with "--".
            lines = [ln for ln in raw_statement.split("\n") if not ln.strip().startswith("--")]
            statement = "\n".join(lines).strip()
            if statement:
                try:
                    cursor.execute(statement)
                except pyodbc.ProgrammingError as e:
                    if "There is already an object named" in str(e):
                        continue
                    raise
    logger.info("Workspace schema applied to '%s'", db_name)


def _grant_mi_access(sql_server: str, db_name: str) -> None:
    """Grant the managed identity db_datareader and db_datawriter roles.

    Uses FROM EXTERNAL PROVIDER (Craig-dependent assumption).
    Non-fatal on failure — admin can grant manually.
    """
    settings = get_settings()
    control_db = settings.control_db_name
    # Derive container app name: 'marshall-mi-control' → 'mi-marshall'
    if control_db.endswith("-mi-control"):
        client_prefix = control_db[: -len("-mi-control")]
        app_name = f"mi-{client_prefix}"
    else:
        logger.warning(
            "Cannot derive app name from control_db_name '%s' — skipping MI grant",
            control_db,
        )
        return

    token_struct = _get_azure_token_struct()
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={sql_server};"
        f"DATABASE={db_name};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    SQL_COPT_SS_ACCESS_TOKEN = 1256
    conn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
    conn.autocommit = True
    try:
        cursor = conn.cursor()
        cursor.execute(f"CREATE USER [{app_name}] FROM EXTERNAL PROVIDER")
        cursor.execute(f"ALTER ROLE db_datareader ADD MEMBER [{app_name}]")
        cursor.execute(f"ALTER ROLE db_datawriter ADD MEMBER [{app_name}]")
        logger.info("Granted MI access for '%s' on database '%s'", app_name, db_name)
    except pyodbc.ProgrammingError as e:
        if "already exists" in str(e).lower():
            logger.info("MI user '%s' already exists on '%s'", app_name, db_name)
        else:
            raise
    finally:
        conn.close()


# ==========================================================================
# Workspace CRUD (Org Admin only)
# ==========================================================================

@admin_router.post("/workspaces")
async def create_workspace(
    body: WorkspaceCreate,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Create a new workspace: SQL database + schema + control DB registration."""
    check_permission(ctx, "manage_workspace")

    settings = get_settings()
    db_name = _derive_db_name(body.name)

    # 1. Check for duplicate name or db_name
    with get_control_db() as cursor:
        cursor.execute(
            "SELECT id FROM workspaces WHERE name = ? OR db_name = ?",
            (body.name, db_name),
        )
        if cursor.fetchone():
            raise HTTPException(409, f"Workspace '{body.name}' or database '{db_name}' already exists")

    # 2. Create the SQL database on the server
    try:
        _create_workspace_database(settings.azure_sql_server, db_name)
    except Exception as e:
        logger.error("Failed to create database '%s': %s", db_name, e, exc_info=True)
        raise HTTPException(500, f"Failed to create workspace database: {e}")

    # 3. Run workspace schema on the new database
    try:
        _run_workspace_schema(db_name)
    except Exception as e:
        logger.error("Failed to run schema on '%s': %s", db_name, e, exc_info=True)
        raise HTTPException(500, f"Database created but schema migration failed: {e}")

    # 4. Grant managed identity access (non-fatal on failure)
    try:
        _grant_mi_access(settings.azure_sql_server, db_name)
    except Exception as e:
        logger.warning(
            "Failed to grant MI access on '%s': %s (may need manual grant)", db_name, e,
        )

    # 5. Register in control DB
    with get_control_db() as cursor:
        cursor.execute(
            """
            INSERT INTO workspaces (name, display_name, db_name, created_by)
            OUTPUT inserted.id, inserted.name, inserted.display_name,
                   inserted.db_name, inserted.is_default, inserted.is_archived,
                   inserted.created_at
            VALUES (?, ?, ?, ?)
            """,
            (body.name, body.display_name, db_name, ctx.user_email),
        )
        row = cursor.fetchone()
        result = {
            "id": row[0],
            "name": row[1],
            "display_name": row[2],
            "db_name": row[3],
            "is_default": bool(row[4]),
            "is_archived": bool(row[5]),
            "created_at": row[6].isoformat() if row[6] else None,
        }

        log_audit(
            cursor, ctx, "create", "workspace", row[0],
            f"Created workspace '{body.display_name}' (db: {db_name})",
        )

    return result


@admin_router.get("/workspaces")
async def list_workspaces(
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """List all workspaces. Org Admin sees all; others see their memberships."""
    check_permission(ctx, "read")

    with get_control_db() as cursor:
        if ctx.is_org_admin:
            cursor.execute(
                """
                SELECT id, name, display_name, db_name, is_default,
                       is_archived, created_at, created_by
                FROM workspaces
                ORDER BY is_default DESC, name
                """
            )
        else:
            cursor.execute(
                """
                SELECT w.id, w.name, w.display_name, w.db_name, w.is_default,
                       w.is_archived, w.created_at, w.created_by
                FROM workspaces w
                JOIN workspace_members wm ON wm.workspace_id = w.id
                JOIN users u ON u.id = wm.user_id
                WHERE u.email = ?
                ORDER BY w.is_default DESC, w.name
                """,
                (ctx.user_email,),
            )
        rows = cursor.fetchall()
        workspaces = [
            {
                "id": row[0],
                "name": row[1],
                "display_name": row[2],
                "db_name": row[3],
                "is_default": bool(row[4]),
                "is_archived": bool(row[5]),
                "created_at": row[6].isoformat() if row[6] else None,
                "created_by": row[7],
            }
            for row in rows
        ]
    return {"workspaces": workspaces, "count": len(workspaces)}


@admin_router.patch("/workspaces/{workspace_id}")
async def archive_workspace(
    workspace_id: int,
    body: WorkspaceArchive,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Archive or unarchive a workspace. Org Admin only."""
    check_permission(ctx, "manage_workspace")

    with get_control_db() as cursor:
        if body.is_archived:
            cursor.execute(
                """
                UPDATE workspaces
                SET is_archived = 1, archived_at = SYSUTCDATETIME()
                WHERE id = ? AND is_archived = 0
                """,
                (workspace_id,),
            )
        else:
            cursor.execute(
                """
                UPDATE workspaces
                SET is_archived = 0, archived_at = NULL
                WHERE id = ? AND is_archived = 1
                """,
                (workspace_id,),
            )
        if cursor.rowcount == 0:
            raise HTTPException(
                404, f"Workspace {workspace_id} not found or already in requested state",
            )

        action = "archived" if body.is_archived else "unarchived"
        log_audit(cursor, ctx, "update", "workspace", workspace_id, f"Workspace {action}")

    return {"message": f"Workspace {action}", "workspace_id": workspace_id}


@admin_router.get("/workspaces/{workspace_id}/audit")
async def get_workspace_audit(
    workspace_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """View audit log for a workspace. Org Admin or Chair of that workspace."""
    if not ctx.is_org_admin:
        is_chair = any(
            m.workspace_id == workspace_id and m.role == "chair"
            for m in ctx.memberships
        )
        if not is_chair:
            raise HTTPException(403, "Only org admins or workspace chairs can view audit logs")

    with get_control_db() as cursor:
        cursor.execute(
            """
            SELECT id, user_email, workspace_name, operation, entity_type,
                   entity_id, detail, timestamp, auth_method
            FROM audit_log
            WHERE workspace_id = ?
            ORDER BY timestamp DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            (workspace_id, offset, limit),
        )
        rows = cursor.fetchall()
        entries = [
            {
                "id": row[0],
                "user_email": row[1],
                "workspace_name": row[2],
                "operation": row[3],
                "entity_type": row[4],
                "entity_id": row[5],
                "detail": row[6],
                "timestamp": row[7].isoformat() if row[7] else None,
                "auth_method": row[8],
            }
            for row in rows
        ]
    return {"entries": entries, "count": len(entries)}


# ==========================================================================
# Member Management (Chair + Org Admin)
# ==========================================================================

@admin_router.post("/workspaces/{workspace_id}/members")
async def add_member(
    workspace_id: int,
    body: MemberAdd,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Add a member to a workspace. Creates user record if needed."""
    _check_member_permission(ctx, workspace_id)

    with get_control_db() as cursor:
        # Verify workspace exists
        cursor.execute("SELECT id, name FROM workspaces WHERE id = ?", (workspace_id,))
        ws_row = cursor.fetchone()
        if not ws_row:
            raise HTTPException(404, f"Workspace {workspace_id} not found")

        # Get or create user
        cursor.execute("SELECT id FROM users WHERE email = ?", (body.email,))
        user_row = cursor.fetchone()
        if user_row:
            user_id = user_row[0]
            # Update display_name if provided and not already set
            if body.display_name:
                cursor.execute(
                    "UPDATE users SET display_name = ? WHERE id = ? AND (display_name IS NULL OR display_name = '')",
                    (body.display_name, user_id),
                )
        else:
            cursor.execute(
                """
                INSERT INTO users (email, display_name, created_by)
                OUTPUT inserted.id
                VALUES (?, ?, ?)
                """,
                (body.email, body.display_name, ctx.user_email),
            )
            user_id = cursor.fetchone()[0]

        # Check for existing membership
        cursor.execute(
            "SELECT id FROM workspace_members WHERE user_id = ? AND workspace_id = ?",
            (user_id, workspace_id),
        )
        if cursor.fetchone():
            raise HTTPException(409, f"User '{body.email}' is already a member of this workspace")

        # Create membership
        cursor.execute(
            """
            INSERT INTO workspace_members (user_id, workspace_id, role, added_by)
            OUTPUT inserted.id
            VALUES (?, ?, ?, ?)
            """,
            (user_id, workspace_id, body.role, ctx.user_email),
        )
        membership_id = cursor.fetchone()[0]

        log_audit(
            cursor, ctx, "create", "member", membership_id,
            f"Added {body.email} as {body.role} to workspace {ws_row[1]}",
        )

    return {
        "message": f"Added {body.email} as {body.role}",
        "user_id": user_id,
        "membership_id": membership_id,
        "workspace_id": workspace_id,
    }


@admin_router.get("/workspaces/{workspace_id}/members")
async def list_members(
    workspace_id: int,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """List members of a workspace."""
    _check_member_permission(ctx, workspace_id)

    with get_control_db() as cursor:
        cursor.execute(
            """
            SELECT wm.id, u.id AS user_id, u.email, u.display_name, wm.role,
                   wm.added_at, wm.added_by, u.is_org_admin
            FROM workspace_members wm
            JOIN users u ON u.id = wm.user_id
            WHERE wm.workspace_id = ?
            ORDER BY
                CASE wm.role WHEN 'chair' THEN 1 WHEN 'member' THEN 2 WHEN 'viewer' THEN 3 END,
                u.email
            """,
            (workspace_id,),
        )
        rows = cursor.fetchall()
        members = [
            {
                "membership_id": row[0],
                "user_id": row[1],
                "email": row[2],
                "display_name": row[3],
                "role": row[4],
                "added_at": row[5].isoformat() if row[5] else None,
                "added_by": row[6],
                "is_org_admin": bool(row[7]),
            }
            for row in rows
        ]
    return {"members": members, "count": len(members)}


@admin_router.patch("/workspaces/{workspace_id}/members/{user_id}")
async def update_member_role(
    workspace_id: int,
    user_id: int,
    body: MemberRoleUpdate,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Change a member's role in a workspace."""
    _check_member_permission(ctx, workspace_id)

    with get_control_db() as cursor:
        cursor.execute(
            "UPDATE workspace_members SET role = ? WHERE user_id = ? AND workspace_id = ?",
            (body.role, user_id, workspace_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(404, "Membership not found")

        log_audit(
            cursor, ctx, "update", "member", user_id,
            f"Changed role to {body.role} in workspace {workspace_id}",
        )

    return {"message": f"Role updated to {body.role}", "user_id": user_id}


@admin_router.delete("/workspaces/{workspace_id}/members/{user_id}")
async def remove_member(
    workspace_id: int,
    user_id: int,
    user: str = Depends(authenticate_and_store),
    ctx: WorkspaceContext = Depends(resolve_workspace),
):
    """Remove a member from a workspace."""
    _check_member_permission(ctx, workspace_id)

    with get_control_db() as cursor:
        # Check the member exists and get their role
        cursor.execute(
            "SELECT role FROM workspace_members WHERE user_id = ? AND workspace_id = ?",
            (user_id, workspace_id),
        )
        member_row = cursor.fetchone()
        if not member_row:
            raise HTTPException(404, "Membership not found")

        # Prevent removing the only chair
        if member_row[0] == "chair":
            cursor.execute(
                """
                SELECT COUNT(*) FROM workspace_members
                WHERE workspace_id = ? AND role = 'chair' AND user_id != ?
                """,
                (workspace_id, user_id),
            )
            other_chairs = cursor.fetchone()[0]
            if other_chairs == 0:
                raise HTTPException(400, "Cannot remove the only chair of a workspace")

        cursor.execute(
            "DELETE FROM workspace_members WHERE user_id = ? AND workspace_id = ?",
            (user_id, workspace_id),
        )

        log_audit(
            cursor, ctx, "delete", "member", user_id,
            f"Removed from workspace {workspace_id}",
        )

    return {"message": "Member removed", "user_id": user_id}

# P7 Workspace Architecture — Pre-Work Package

**Date:** 25 February 2026
**Purpose:** Everything the repo-side agent needs to execute the workspace build. One prompt per phase, exact specs, no ambiguity.
**Status:** Complete — sprint-ready (Craig confirmation pending on 2 assumed defaults)
**Companion doc:** `Brief_MI Multi Database Architecture_Draft_24FEB26.md`

---

## 0. Preflight Check (W0)

Run this BEFORE any code changes. Confirms the baseline is green on the feature branch.

### W0 Prompt

```
CONTEXT:
You are about to begin P7: Workspace Architecture on the Meeting Intelligence system.
Before writing any code, verify the baseline is healthy. Do NOT proceed to W1 until
every check below passes.

CHECKS:

1. Branch confirmation:
   - Run: git branch --show-current
   - MUST be on feature/p7-workspaces (or the agreed feature branch name)
   - If on main or any other branch, STOP and ask for instructions

2. Test suite:
   - Run: pytest
   - ALL existing tests must pass (expect 101)
   - Record exact count and any skips
   - If ANY test fails, STOP — do not proceed. Report failures.

3. App startup:
   - Run: python -m server.src.main --http (or however the app starts)
   - Must start without errors
   - If it fails, STOP and report the error

4. Health endpoint:
   - Run: curl http://localhost:8000/api/health (or equivalent)
   - Must return 200
   - If it fails, STOP and report

5. Snapshot baseline metrics:
   - Record: test count, file count in server/src/, file count in server/src/tools/
   - Record: python --version, pip list | grep -E "fastapi|pyodbc|sqlalchemy|msal"
   - These are reference numbers for post-build comparison

OUTPUT:
Report all results in a summary table:

| Check | Result | Detail |
|-------|--------|--------|
| Branch | ✅/❌ | branch name |
| Tests | ✅/❌ | X passed, Y failed, Z skipped |
| App start | ✅/❌ | clean / error message |
| Health | ✅/❌ | status code |
| Python version | — | X.Y.Z |
| FastAPI version | — | X.Y.Z |
| PyODBC version | — | X.Y.Z |
| SQLAlchemy version | — | X.Y.Z |

If all checks pass: "Preflight GREEN. Ready for W1."
If any check fails: "Preflight FAILED. Do not proceed." + details.
```

---

## 1. Control Database SQL DDL

This is the foundation. Every other component references these tables.

```sql
-- =============================================================================
-- MI Control Database Schema
-- Run against: {client}-mi-control database on the client's SQL Server
-- Prerequisites: Entra admin set on SQL Server, managed identity granted access
-- =============================================================================

-- Workspaces: one row per workspace (= one database)
CREATE TABLE workspaces (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    name            NVARCHAR(100)   NOT NULL UNIQUE,   -- slug: 'board', 'ceo', 'ops'
    display_name    NVARCHAR(255)   NOT NULL,           -- 'Board', 'CEO Office', 'Operations'
    db_name         NVARCHAR(128)   NOT NULL UNIQUE,   -- actual Azure SQL database name
    is_default      BIT             NOT NULL DEFAULT 0, -- exactly one row should be 1 (General)
    is_archived     BIT             NOT NULL DEFAULT 0, -- archived = read-only, no new data
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    created_by      NVARCHAR(255)   NOT NULL,           -- email of creator
    archived_at     DATETIME2       NULL
);

-- Users: one row per person who accesses the system via MCP token
-- Web users (Azure AD) may not have a row here — they resolve via AD groups
-- But if they also use MCP, they need a row for token linkage
CREATE TABLE users (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    email           NVARCHAR(255)   NOT NULL UNIQUE,
    display_name    NVARCHAR(255)   NULL,
    is_org_admin    BIT             NOT NULL DEFAULT 0, -- cross-workspace super-user
    default_workspace_id INT        NULL,               -- FK to workspaces.id
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    created_by      NVARCHAR(255)   NOT NULL,

    CONSTRAINT FK_users_default_workspace
        FOREIGN KEY (default_workspace_id) REFERENCES workspaces(id)
);

-- Workspace memberships: many-to-many between users and workspaces
CREATE TABLE workspace_members (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    user_id         INT             NOT NULL,
    workspace_id    INT             NOT NULL,
    role            NVARCHAR(20)    NOT NULL,           -- 'viewer', 'member', 'chair'
    added_at        DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    added_by        NVARCHAR(255)   NOT NULL,           -- email of who added them

    CONSTRAINT FK_wm_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT FK_wm_workspace FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE,
    CONSTRAINT UQ_wm_user_workspace UNIQUE (user_id, workspace_id),
    CONSTRAINT CK_wm_role CHECK (role IN ('viewer', 'member', 'chair'))
);

-- Tokens: MCP authentication tokens, linked to users
-- Moved from workspace databases to control database
CREATE TABLE tokens (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    token_hash      NVARCHAR(64)    NOT NULL UNIQUE,   -- SHA256 hex
    user_id         INT             NOT NULL,
    client_name     NVARCHAR(255)   NULL,               -- legacy compat: display name
    is_active       BIT             NOT NULL DEFAULT 1,
    created_at      DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    created_by      NVARCHAR(255)   NOT NULL,
    expires_at      DATETIME2       NULL,               -- NULL = no expiry
    revoked_at      DATETIME2       NULL,
    notes           NVARCHAR(500)   NULL,

    CONSTRAINT FK_tokens_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Audit log: every data access logged
CREATE TABLE audit_log (
    id              BIGINT IDENTITY(1,1) PRIMARY KEY,
    user_email      NVARCHAR(255)   NOT NULL,
    workspace_id    INT             NULL,               -- NULL for cross-workspace ops
    workspace_name  NVARCHAR(100)   NULL,               -- denormalised for query speed
    operation       NVARCHAR(50)    NOT NULL,           -- 'read', 'create', 'update', 'delete'
    entity_type     NVARCHAR(50)    NOT NULL,           -- 'meeting', 'action', 'decision', 'workspace', 'member'
    entity_id       INT             NULL,               -- ID of the entity, NULL for list ops
    detail          NVARCHAR(500)   NULL,               -- optional context
    timestamp       DATETIME2       NOT NULL DEFAULT SYSUTCDATETIME(),
    auth_method     NVARCHAR(20)    NOT NULL            -- 'mcp', 'web', 'oauth', 'admin'
);

-- Indexes for common query patterns
CREATE INDEX IX_wm_user_id ON workspace_members(user_id);
CREATE INDEX IX_wm_workspace_id ON workspace_members(workspace_id);
CREATE INDEX IX_tokens_hash ON tokens(token_hash) WHERE is_active = 1;
CREATE INDEX IX_tokens_user ON tokens(user_id);
CREATE INDEX IX_audit_user ON audit_log(user_email, timestamp DESC);
CREATE INDEX IX_audit_workspace ON audit_log(workspace_id, timestamp DESC);
CREATE INDEX IX_audit_timestamp ON audit_log(timestamp DESC);

-- Seed the General workspace (default, created during deployment)
-- db_name will be set by the deploy script based on client name
-- INSERT INTO workspaces (name, display_name, db_name, is_default, created_by)
-- VALUES ('general', 'General', '{client}-mi-general', 1, 'system@generationai.co.nz');
```

**Notes:**
- `workspaces.db_name` is the actual Azure SQL database name (e.g., `acme-mi-board`). The engine registry uses this to create connections.
- `tokens` table replaces `ClientToken` in workspace databases. During migration, existing tokens move here.
- `audit_log` uses BIGINT for id — will grow fast. Consider retention policy (90 days? 1 year?).
- The seed INSERT is commented out — the deploy script fills in the actual db_name.

---

## 2. Python Interface Specs

These are the contracts. The agent writes the implementations. Every other file programs against these.

### 2a. WorkspaceContext (dataclass)

```python
# File: server/src/workspace_context.py (new)

from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class WorkspaceMembership:
    """One user's membership in one workspace."""
    workspace_id: int
    workspace_name: str          # slug: 'board', 'ceo', 'ops'
    workspace_display_name: str  # 'Board', 'CEO Office', 'Operations'
    db_name: str                 # actual Azure SQL database name
    role: str                    # 'viewer', 'member', 'chair'
    is_default: bool             # is this the user's default workspace?
    is_archived: bool            # archived workspaces are read-only

@dataclass(frozen=True)
class WorkspaceContext:
    """Resolved per-request. Immutable for the duration of the request."""
    user_email: str
    is_org_admin: bool
    memberships: list[WorkspaceMembership]    # all workspaces user belongs to
    active: WorkspaceMembership               # the workspace for this request

    @property
    def role(self) -> str:
        """Shortcut: role in the active workspace."""
        return self.active.role

    @property
    def db_name(self) -> str:
        """Shortcut: database name of the active workspace."""
        return self.active.db_name

    def can_write(self) -> bool:
        """Can the user write in the active workspace?"""
        if self.is_org_admin:
            return True
        if self.active.is_archived:
            return False
        return self.active.role in ('member', 'chair')

    def is_chair_or_admin(self) -> bool:
        """Can the user manage/delete in the active workspace?"""
        return self.is_org_admin or self.active.role == 'chair'
```

### 2b. EngineRegistry

```python
# Added to: server/src/database.py (replaces global _engine pattern)

import threading
import pyodbc
pyodbc.pooling = False  # CRITICAL: must be before any connections

from sqlalchemy import create_engine, Engine
from sqlalchemy.pool import QueuePool

class EngineRegistry:
    """Thread-safe lazy engine cache. One engine per database on the same SQL Server."""

    def __init__(self, sql_server: str, pool_size: int = 3, max_overflow: int = 1):
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()
        self._sql_server = sql_server
        self._pool_size = pool_size
        self._max_overflow = max_overflow

    def get_engine(self, database_name: str) -> Engine:
        """Get or create an engine for the given database. Thread-safe, lazy."""
        if database_name in self._engines:
            return self._engines[database_name]
        with self._lock:
            if database_name not in self._engines:
                self._engines[database_name] = self._create_engine(database_name)
            return self._engines[database_name]

    def _create_engine(self, database_name: str) -> Engine:
        """Create a new SQLAlchemy engine for a specific database."""
        # Uses the same pattern as the current _get_engine(), but parameterised
        # Connection factory uses DefaultAzureCredential + pyodbc
        # Pool settings constrained for multi-engine scenario
        ...  # Agent implements — see current _get_engine() and _create_raw_connection()

    def dispose_all(self) -> None:
        """Dispose all engines. Called on app shutdown."""
        with self._lock:
            for engine in self._engines.values():
                engine.dispose()
            self._engines.clear()

    @property
    def engine_count(self) -> int:
        return len(self._engines)

# Module-level singleton, initialised in main.py or on first use
engine_registry: EngineRegistry = None  # set during app startup
```

### 2c. get_db_for() context manager

```python
# Added to: server/src/database.py

from contextlib import contextmanager
from typing import Generator

@contextmanager
def get_db_for(engine: Engine) -> Generator[pyodbc.Cursor, None, None]:
    """Yield a pyodbc cursor from a specific engine. Same pattern as current get_db()."""
    conn = engine.raw_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

@contextmanager
def get_control_db() -> Generator[pyodbc.Cursor, None, None]:
    """Shortcut: cursor for the control database."""
    settings = get_settings()
    engine = engine_registry.get_engine(settings.control_db_name)
    with get_db_for(engine) as cursor:
        yield cursor

# Keep existing get_db() as backward compat during transition
# It uses AZURE_SQL_DATABASE (the default workspace)
@contextmanager
def get_db() -> Generator[pyodbc.Cursor, None, None]:
    """Legacy: cursor for the default workspace database."""
    settings = get_settings()
    engine = engine_registry.get_engine(settings.azure_sql_database)
    with get_db_for(engine) as cursor:
        yield cursor
```

### 2d. FastAPI Dependencies (Depends() chain)

```python
# File: server/src/dependencies.py (new)

from fastapi import Depends, Header, HTTPException, Request
from typing import Optional, Generator
import pyodbc

from .database import engine_registry, get_db_for, get_control_db
from .workspace_context import WorkspaceContext, WorkspaceMembership
from .config import get_settings

# --- Layer 1: Authenticate ---

async def authenticate_web(request: Request) -> str:
    """Azure AD JWT → email. Uses existing fastapi_azure_auth flow."""
    # Reuses logic from api.py get_current_user()
    # Returns user email string
    ...

async def authenticate_mcp(request: Request) -> str:
    """MCP Bearer token → control DB lookup → user email."""
    # Reuses logic from main.py mcp_auth_middleware
    # But validates against control DB tokens table, not workspace DB
    # Returns user email string
    ...

# --- Layer 2: Resolve workspace ---

def _get_user_memberships(cursor: pyodbc.Cursor, email: str) -> tuple[bool, list[WorkspaceMembership]]:
    """Query control DB: user → is_org_admin + workspace memberships."""
    # Returns (is_org_admin, [WorkspaceMembership, ...])
    # SQL joins users → workspace_members → workspaces
    ...

def _resolve_active_workspace(
    memberships: list[WorkspaceMembership],
    requested: Optional[str],
    default_workspace_id: Optional[int]
) -> WorkspaceMembership:
    """Pick the active workspace from: explicit request > user default > first membership."""
    ...

async def resolve_workspace(
    request: Request,
    x_workspace_id: Optional[str] = Header(None, alias="X-Workspace-ID"),
) -> WorkspaceContext:
    """Full workspace resolution. Produces the immutable WorkspaceContext for this request."""
    # 1. Get user email from request (set by auth layer)
    # 2. Query control DB for memberships
    # 3. Resolve active workspace
    # 4. Return WorkspaceContext
    ...

# --- Layer 3: Get workspace-scoped DB cursor ---

def get_workspace_db(ctx: WorkspaceContext = Depends(resolve_workspace)) -> Generator[pyodbc.Cursor, None, None]:
    """Yield a pyodbc cursor connected to the active workspace database."""
    engine = engine_registry.get_engine(ctx.db_name)
    with get_db_for(engine) as cursor:
        yield cursor
```

### 2e. Permission Enforcer

```python
# File: server/src/permissions.py (new)

from fastapi import HTTPException
from .workspace_context import WorkspaceContext

def check_permission(ctx: WorkspaceContext, operation: str, entity: dict = None) -> None:
    """
    Check if current user can perform the operation in their active workspace.

    Operations: 'read', 'create', 'update', 'delete', 'manage_members', 'manage_workspace'
    Entity: dict with at least 'created_by' key for ownership checks. None for list/create ops.

    Raises HTTPException 403 if denied. Returns None if allowed.
    """

    # Org admin bypasses everything
    if ctx.is_org_admin:
        return

    role = ctx.role  # viewer | member | chair

    # Archived workspace: read-only for everyone
    if ctx.active.is_archived and operation != 'read':
        raise HTTPException(403, f"Workspace '{ctx.active.workspace_display_name}' is archived (read-only)")

    # Read: all roles
    if operation == 'read':
        return

    # Create: member + chair
    if operation == 'create':
        if role == 'viewer':
            raise HTTPException(403, "Viewers cannot create items")
        return

    # Update: member (own only) + chair (any)
    if operation == 'update':
        if role == 'viewer':
            raise HTTPException(403, "Viewers cannot edit items")
        if role == 'member' and entity and entity.get('created_by') != ctx.user_email:
            raise HTTPException(403, "Members can only edit their own items")
        return

    # Delete: chair only
    if operation == 'delete':
        if role in ('viewer', 'member'):
            raise HTTPException(403, "Only chairs can delete items")
        return

    # Manage members: chair only
    if operation == 'manage_members':
        if role != 'chair':
            raise HTTPException(403, "Only chairs can manage workspace members")
        return

    # Manage workspace (create/archive): org admin only (already handled above)
    if operation == 'manage_workspace':
        raise HTTPException(403, "Only org admins can manage workspaces")
```

### 2f. MCP Contextvars Extension

```python
# Added to: server/src/mcp_server.py (extends existing pattern)

import contextvars
from .workspace_context import WorkspaceContext

# Existing
_mcp_user_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "mcp_user", default="system@generationai.co.nz"
)

# New: full workspace context
_mcp_workspace_ctx_var: contextvars.ContextVar[WorkspaceContext | None] = contextvars.ContextVar(
    "mcp_workspace_ctx", default=None
)

def set_mcp_user(email: str) -> None:
    _mcp_user_var.set(email)

def get_mcp_user() -> str:
    return _mcp_user_var.get()

def set_mcp_workspace_context(ctx: WorkspaceContext) -> None:
    _mcp_workspace_ctx_var.set(ctx)

def get_mcp_workspace_context() -> WorkspaceContext:
    ctx = _mcp_workspace_ctx_var.get()
    if ctx is None:
        raise RuntimeError("MCP workspace context not set — auth middleware did not resolve workspace")
    return ctx
```

### 2g. Config Addition

```python
# Added to: server/src/config.py Settings class

class Settings(BaseSettings):
    # ... existing fields ...
    control_db_name: str = ""  # e.g., 'acme-mi-control'. Empty = workspace features disabled.
```

---

## 3. Per-Phase Implementation Prompts

### Phase W1 Prompt — Foundation

```
CONTEXT:
You are working on the Meeting Intelligence system. We are implementing P7: Workspace Architecture.
This is Phase W1 (Foundation). The goal is to add the control database schema, engine registry,
FastAPI dependency chain, MCP context extension, and permission enforcer.

After this phase, the app should start, connect to a control database, and be able to resolve
a user to their workspace context. No tool functions are modified yet — existing functionality
must continue to work via the legacy get_db() path.

CRITICAL PREREQUISITE:
Add `import pyodbc; pyodbc.pooling = False` at the TOP of database.py, before any other pyodbc
or sqlalchemy imports. This disables pyodbc's hidden connection pooling which conflicts with
SQLAlchemy's pool. Without this, connection limits are meaningless.

FILES TO CREATE:
1. scripts/control_schema.sql — [EXACT DDL FROM SECTION 1 ABOVE]
2. server/src/workspace_context.py — [EXACT SPEC FROM SECTION 2a]
3. server/src/dependencies.py — [EXACT SPEC FROM SECTION 2d]
4. server/src/permissions.py — [EXACT SPEC FROM SECTION 2e]

FILES TO MODIFY:
5. server/src/database.py:
   - Add `pyodbc.pooling = False` at module top (before any imports that trigger connections)
   - Add EngineRegistry class [SPEC FROM SECTION 2b]
   - Add get_db_for(engine) context manager [SPEC FROM SECTION 2c]
   - Add get_control_db() shortcut [SPEC FROM SECTION 2c]
   - Keep existing get_db() working (backward compat) — refactor it to use EngineRegistry internally
   - Keep ALL existing functions (validate_client_token, create_client_token, etc.) working
   - The EngineRegistry._create_engine() method should use the same connection pattern as the
     existing _create_raw_connection() function, but parameterised for any database name.
     Pool settings: pool_size=3, max_overflow=1, pool_timeout=30, pool_recycle=1800,
     pool_pre_ping=True, pool_use_lifo=True

6. server/src/config.py:
   - Add `control_db_name: str = ""` to Settings class

7. server/src/mcp_server.py:
   - Add _mcp_workspace_ctx_var ContextVar [SPEC FROM SECTION 2f]
   - Add set_mcp_workspace_context() and get_mcp_workspace_context() functions
   - Keep ALL existing tool registrations and functions working — do not modify them yet

8. server/src/main.py:
   - Initialise engine_registry during app startup (in lifespan or at module level)
   - If control_db_name is set in config, create the registry with the SQL server from config
   - Update mcp_auth_middleware: if control_db_name is configured, resolve workspace context
     from control DB and call set_mcp_workspace_context(). Fall back to existing behaviour
     if control_db_name is empty.

IMPORTANT CONSTRAINTS:
- All existing tests (101) must continue to pass
- All existing MCP tools must continue to work
- All existing API endpoints must continue to work
- The control database features are ADDITIVE — if control_db_name is empty, the app
  behaves exactly as before (single database mode)
- Do NOT modify any tool functions in tools/*.py yet — that's Phase W2

GATE CHECK (verify these after implementation):
- [ ] App starts without errors
- [ ] All 101 existing tests pass
- [ ] `GET /api/health` returns 200
- [ ] EngineRegistry creates engines lazily (no connections on startup)
- [ ] get_db() still works (backward compat)
- [ ] get_db_for(engine) works with a manually created engine
- [ ] WorkspaceContext can be instantiated with test data
- [ ] check_permission() raises 403 for viewer creating an item
- [ ] check_permission() passes for member creating an item
- [ ] check_permission() passes for org admin on any operation
- [ ] pyodbc.pooling is False (verify with `assert pyodbc.pooling == False`)
```

### Phase W2 Prompt — Tool Refactor + api.py Consolidation

```
CONTEXT:
Continuing P7 Workspace Architecture. Phase W1 is complete — engine registry, dependencies,
permissions, and workspace context are in place. This is Phase W2: wire every tool function
and API endpoint through the workspace-scoped cursor and permission system.

CURRENT STATE OF TOOL FUNCTIONS (from codebase snapshot):
Every function in tools/meetings.py, tools/actions.py, tools/decisions.py follows this pattern:
  @retry_on_transient()
  def some_function(param1, param2, ...) -> dict:
      with get_db() as cursor:
          cursor.execute("SQL ...")
          ...

TARGET STATE:
Every function receives cursor and ctx as first two params:
  @retry_on_transient()
  def some_function(cursor, ctx: WorkspaceContext, param1, param2, ...) -> dict:
      check_permission(ctx, "read")  # or "create", "update", "delete"
      cursor.execute("SQL ...")
      ...

The `with get_db() as cursor:` block is REMOVED from inside the function.
The cursor comes from the caller (Depends() chain for API, contextvars for MCP).

FILES TO MODIFY:

1. server/src/tools/meetings.py — Refactor ALL 6 functions:
   - list_meetings(cursor, ctx, limit, days_back, attendee, tag) — check_permission(ctx, "read")
   - get_meeting(cursor, ctx, meeting_id) — check_permission(ctx, "read")
   - search_meetings(cursor, ctx, query, limit) — check_permission(ctx, "read")
   - create_meeting(cursor, ctx, title, meeting_date, ...) — check_permission(ctx, "create")
     Note: user_email param is replaced by ctx.user_email
   - update_meeting(cursor, ctx, meeting_id, ...) — check_permission(ctx, "update", entity)
     Must fetch entity first to check ownership for member role
   - delete_meeting(cursor, ctx, meeting_id) — check_permission(ctx, "delete")
   - Remove `from ..database import get_db` import
   - Add `from ..workspace_context import WorkspaceContext` and `from ..permissions import check_permission`

2. server/src/tools/actions.py — Refactor ALL 9 functions:
   - list_actions(cursor, ctx, status, owner, meeting_id, limit) — "read"
   - get_distinct_owners(cursor, ctx) — "read"
   - get_action(cursor, ctx, action_id) — "read"
   - search_actions(cursor, ctx, query, limit) — "read"
   - create_action(cursor, ctx, action_text, owner, ...) — "create"
   - update_action(cursor, ctx, action_id, ...) — "update" with entity ownership check
   - complete_action(cursor, ctx, action_id) — "update" with entity ownership check
   - park_action(cursor, ctx, action_id) — "update" with entity ownership check
   - delete_action(cursor, ctx, action_id) — "delete"

3. server/src/tools/decisions.py — Refactor ALL 5 functions:
   - list_decisions(cursor, ctx, meeting_id, limit) — "read"
   - get_decision(cursor, ctx, decision_id) — "read"
   - search_decisions(cursor, ctx, query, limit) — "read"
   - create_decision(cursor, ctx, meeting_id, decision_text, ...) — "create"
   - delete_decision(cursor, ctx, decision_id) — "delete"

4. server/src/api.py — CONSOLIDATE + WIRE:
   - Move ALL inline SQL into tool functions:
     * delete_meeting cascade → new meetings.delete_meeting_cascade(cursor, ctx, meeting_id)
     * delete_action raw SQL → use actions.delete_action(cursor, ctx, action_id)
     * delete_decision raw SQL → use decisions.delete_decision(cursor, ctx, decision_id)
     * Status update to "Open" raw SQL → new actions.reopen_action(cursor, ctx, action_id)
     * Meeting detail (get_meeting + linked decisions/actions) → new meetings.get_meeting_detail(cursor, ctx, meeting_id)
   - All endpoints use Depends(resolve_workspace) and Depends(get_workspace_db)
   - All endpoints pass cursor and ctx to tool functions
   - Remove direct get_db() usage from api.py entirely

5. server/src/mcp_server.py — WIRE ALL 20 TOOLS:
   Each tool handler:
   - Retrieves WorkspaceContext via get_mcp_workspace_context()
   - Gets engine from engine_registry.get_engine(ctx.db_name)
   - Opens cursor via get_db_for(engine)
   - Passes cursor and ctx to the tool function
   - Add optional `workspace: str | None = None` parameter to each tool
     (allows AI agent to override active workspace)

   Example pattern:
   @mcp.tool(description="...", annotations=READ_ONLY)
   async def list_actions(status=None, owner=None, meeting_id=None, limit=50,
                          workspace: str | None = None) -> dict:
       params = ActionListFilter(status=status, owner=owner, ...)
       ctx = get_mcp_workspace_context()
       if workspace:
           ctx = ctx.with_active_workspace(workspace)  # need to add this method
       engine = engine_registry.get_engine(ctx.db_name)
       with get_db_for(engine) as cursor:
           return actions.list_actions(cursor, ctx, ...)

6. NEW: server/src/tools/workspaces.py — Workspace management tools:
   - list_workspaces(cursor_control, ctx) — returns user's workspaces
   - get_current_workspace(ctx) — returns active workspace info
   These query the CONTROL database, not a workspace database.

7. server/src/mcp_server.py — Add 3 new MCP tools:
   - list_workspaces — calls tools/workspaces.py
   - switch_workspace — updates active workspace in context
   - get_current_workspace — returns active workspace info

IMPORTANT CONSTRAINTS:
- SQL queries inside tool functions DO NOT CHANGE — only the function signatures change
- The @retry_on_transient() decorator stays on all functions
- Permission checks use check_permission() from permissions.py
- For "update" operations on member role, the tool function must fetch the entity first
  to check created_by before proceeding
- All existing Pydantic validation (schemas.py) stays in place

GATE CHECK:
- [ ] All tool functions have cursor + ctx as first two params
- [ ] No tool function imports or calls get_db() internally
- [ ] No inline SQL in api.py — all data access through tools/*.py
- [ ] All 20 MCP tools have optional `workspace` parameter
- [ ] 3 new MCP tools: list_workspaces, switch_workspace, get_current_workspace
- [ ] Permission checks: viewer can read but not create/update/delete
- [ ] Permission checks: member can create, update own, cannot delete
- [ ] Permission checks: chair can do everything in their workspace
- [ ] Archived workspace rejects all writes with 403
- [ ] Existing tests updated to pass cursor + ctx (or mocked)
```

### Phase W3 Prompt — Token Model + Admin

```
CONTEXT:
P7 Phase W3. W1 (foundation) and W2 (tool refactor) are complete. All tools and endpoints
use workspace-scoped cursors and permission enforcement. This phase: user-level tokens,
workspace CRUD admin API, member management, and audit logging.

FILES TO CREATE:

1. server/src/admin.py — Admin API endpoints:
   Workspace CRUD (Org Admin only):
   - POST /api/admin/workspaces — create workspace
     Body: {name, display_name}
     Action: create SQL database on existing server (via pyodbc to master),
             run workspace schema migrations,
             grant MI access via FROM EXTERNAL PROVIDER (⚠️ CRAIG ASSUMED — see Craig-Dependent Items),
             register in control DB
     Returns: workspace record
   - GET /api/admin/workspaces — list all workspaces
   - PATCH /api/admin/workspaces/{id} — archive/unarchive workspace
   - GET /api/admin/workspaces/{id}/audit — view audit log for workspace

   Member management (Chair of workspace + Org Admin):
   - POST /api/admin/workspaces/{id}/members — add member
     Body: {email, display_name, role}
     Action: create user if not exists, create workspace_member record
   - GET /api/admin/workspaces/{id}/members — list members
   - PATCH /api/admin/workspaces/{id}/members/{user_id} — change role
   - DELETE /api/admin/workspaces/{id}/members/{user_id} — remove member

   All admin endpoints use Depends(resolve_workspace) for auth,
   but query the CONTROL database for data.

2. server/src/audit.py — Audit logging utility:
   def log_audit(cursor_control, ctx: WorkspaceContext, operation: str,
                 entity_type: str, entity_id: int = None, detail: str = None) -> None:
       """Insert a row into audit_log in the control database."""
       ...

   Called from tool functions after successful operations.
   Uses a SEPARATE cursor to the control DB (not the workspace cursor).

FILES TO MODIFY:

3. server/src/database.py:
   - Remove validate_client_token() — replaced by control DB lookup
   - Remove create_client_token(), insert_token_hash(), revoke_client_token(),
     list_client_tokens() — replaced by admin API + manage_tokens.py rewrite
   - Add new function: validate_token_from_control_db(cursor, token_hash) -> dict | None
     Returns: {user_email, is_org_admin, memberships: [...]} or None
   - Keep OAuth functions (save_oauth_client etc.) unchanged

4. server/scripts/manage_tokens.py — REWRITE:
   New CLI interface:
   - create --user EMAIL --workspace WORKSPACE_NAME --role ROLE [--expires DAYS] [--notes TEXT]
     Creates user in control DB if not exists, generates token, assigns workspace membership
   - list — shows all tokens with user info and workspace memberships
   - revoke --token-id ID — revokes token
   - add-membership --user EMAIL --workspace WORKSPACE_NAME --role ROLE
   - remove-membership --user EMAIL --workspace WORKSPACE_NAME
   - list-users — shows all users with their memberships

   Connection: reads AZURE_SQL_SERVER + CONTROL_DB_NAME from env
   Uses its own _get_connection() targeting the control database

5. server/src/main.py:
   - Update token cache: cache WorkspaceContext objects, not just email strings
   - Update mcp_auth_middleware: always resolve from control DB when configured
   - Mount admin API routes: app.include_router(admin_router, prefix="/api/admin")

GATE CHECK:
- [ ] POST /api/admin/workspaces creates a new database on the SQL server
- [ ] New database has the workspace schema (meetings, actions, decisions tables)
- [ ] Managed identity has db_datareader + db_datawriter on new database
- [ ] New workspace registered in control DB
- [ ] manage_tokens.py create --user X --workspace Y --role Z works
- [ ] Token validation returns full WorkspaceContext with memberships
- [ ] Admin endpoints require Org Admin (or Chair for member management)
- [ ] Audit log records operations
- [ ] Non-admin users get 403 on admin endpoints
```

### Phase W4 Prompt — Infrastructure + Ingestion

```
CONTEXT:
P7 Phase W4. W1-W3 complete. The application layer is fully workspace-aware. This phase:
infrastructure (Bicep, deploy scripts), migration tooling, and Fireflies ingestion routing.

FILES TO CREATE:

1. infra/modules/sql-server.bicep — SQL Server + Control DB + General workspace DB:
   - Creates SQL Server with Entra admin
   - Creates control database (Basic tier)
   - Creates General workspace database (Basic tier)
   - Outputs: server name, control DB name, general DB name

2. infra/modules/workspace-db.bicep — Single workspace DB on existing server:
   - Input: server name, database name
   - Creates one SQL Database (Basic tier) on existing server
   - Output: database name

3. scripts/grant-mi-access.sql — T-SQL template (⚠️ CRAIG ASSUMED: FROM EXTERNAL PROVIDER):
   - CREATE USER [container-app-name] FROM EXTERNAL PROVIDER;
   - ALTER ROLE db_datareader ADD MEMBER [container-app-name];
   - ALTER ROLE db_datawriter ADD MEMBER [container-app-name];
   - Parameterised for container app name
   - If Craig overrides to SID-based: replace FROM EXTERNAL PROVIDER with
     WITH SID = <computed-sid>, TYPE = E

4. scripts/migrate-all-workspaces.py:
   - Connects to control DB, discovers all workspace databases
   - Runs schema migration SQL on each workspace database
   - Reports per-database success/failure
   - Exits non-zero if any fail

5. scripts/migrate-to-workspaces.py — Upgrade existing deployment:
   - Creates control database on existing SQL server
   - Runs control_schema.sql
   - Registers existing database as "General" workspace (is_default=1)
   - Migrates tokens from existing ClientToken table to control DB tokens table
   - Creates user records for each token
   - Creates workspace_member records (all existing users → General, role=chair)

FILES TO MODIFY:

6. scripts/deploy-new-client.sh:
   - Replace single sql.bicep call with sql-server.bicep (creates server + control + general)
   - Run control_schema.sql against control database
   - Run workspace schema against general database
   - Grant MI access to both databases (grant-mi-access.sql)
   - Add CONTROL_DB_NAME to container app environment variables
   - Seed General workspace in control DB

7. infra/modules/container-app.bicep:
   - Add CONTROL_DB_NAME environment variable

8. server/src/tools/meetings.py (or webhook handler):
   - Update meeting ingestion (create_meeting) to support workspace routing:
     When source is "Fireflies" or similar external source:
     - Extract organiser email from meeting data
     - Look up organiser in control DB → get their workspace memberships
     - If single workspace: route to that workspace's database
     - If multiple workspaces: route to their default workspace
     - If not found: route to General workspace

GATE CHECK:
- [ ] deploy-new-client.sh creates SQL Server + control DB + General workspace DB
- [ ] Control DB has all 5 tables from control_schema.sql
- [ ] General workspace DB has meetings/actions/decisions tables
- [ ] MI has access to both databases
- [ ] CONTROL_DB_NAME is in container app environment
- [ ] migrate-to-workspaces.py upgrades an existing deployment cleanly
- [ ] Existing tokens are accessible after migration
- [ ] migrate-all-workspaces.py discovers and migrates all workspace DBs
- [ ] Fireflies transcript routes to correct workspace based on organiser
- [ ] Unroutable transcript goes to General workspace
```

### Phase W5 Prompt — Web UI + Testing

```
CONTEXT:
P7 Phase W5. W1-W4 complete. Backend fully workspace-aware, infrastructure provisioned.
This phase: web UI workspace support and comprehensive testing.

WEB UI CHANGES:

1. Workspace switcher component:
   - New React component: WorkspaceSwitcher
   - Dropdown in the app header showing user's workspaces (name + role badge)
   - Fetches workspaces from GET /api/admin/workspaces (or a new /api/me/workspaces endpoint)
   - On switch: stores selected workspace in React state, sets X-Workspace-ID header on all
     subsequent API calls
   - Shows current workspace name in header
   - Org Admin sees "All Workspaces" option (for merged view on read ops)

2. Permission-aware UI:
   - API responses include user's role for the current workspace (add to response headers or body)
   - Hide "Delete" buttons for members and viewers
   - Hide "Edit" buttons for viewers
   - Hide admin panel link for non-chairs/non-org-admins
   - Show role badge next to workspace name: "Chair", "Member", "Viewer"

3. Workspace admin panel (new page):
   - Route: /admin/workspaces
   - Org Admin view: list all workspaces, create new, archive
   - Chair view: list members of their workspace, add/remove members, change roles
   - Uses admin API endpoints from W3

4. API client update:
   - All fetch/axios calls include X-Workspace-ID header from current workspace state
   - Add workspace context to React context/state management

TEST SPECS:

5. tests/test_workspace_isolation.py:
   Test setup: create 2 workspaces (ws_a, ws_b) with separate databases.
   User A: member of ws_a only. User B: member of ws_b only. User C: member of both.

   - User A calls list_meetings → gets only ws_a meetings
   - User A calls list_meetings with workspace=ws_b → gets 403
   - User B calls list_actions → gets only ws_b actions
   - User C calls list_meetings with workspace=ws_a → gets ws_a meetings
   - User C calls list_meetings with workspace=ws_b → gets ws_b meetings
   - User A creates action in ws_a → succeeds
   - User A creates action with workspace=ws_b → 403
   - Meeting created in ws_a is NOT visible from ws_b cursor
   - Action created in ws_b is NOT visible from ws_a cursor

6. tests/test_permissions.py:
   Test setup: 1 workspace. User V (viewer), User M (member), User C (chair), User A (org admin).

   Viewer:
   - list_meetings → 200
   - create_action → 403
   - update_action → 403
   - delete_action → 403

   Member:
   - create_action → 200
   - update own action → 200
   - update other's action → 403
   - delete_action → 403
   - complete own action → 200
   - complete other's action → 403

   Chair:
   - create_action → 200
   - update any action → 200
   - delete any action → 200
   - manage members → 200

   Org Admin:
   - all operations → 200
   - create workspace → 200
   - manage any workspace's members → 200

   Archived workspace:
   - any role: read → 200
   - any role: create/update/delete → 403 "workspace is archived"

7. tests/test_engine_registry.py:
   - EngineRegistry creates engines lazily (count starts at 0)
   - get_engine("db_a") creates 1 engine
   - get_engine("db_a") again returns same engine (no new creation)
   - get_engine("db_b") creates second engine (count = 2)
   - dispose_all() disposes all engines (count = 0)
   - pyodbc.pooling is False
   - Concurrent get_engine() calls from multiple threads: only 1 engine created per db

8. tests/test_token_workspace.py:
   - Token resolves to user with correct workspace memberships
   - Token with revoked status returns None
   - Token with expired timestamp returns None
   - Token resolves is_org_admin correctly
   - Token resolves default_workspace_id correctly

GATE CHECK:
- [ ] Web UI shows workspace switcher with current workspace
- [ ] Switching workspace changes all data views
- [ ] Viewer cannot see edit/delete buttons
- [ ] Admin panel accessible to chairs and org admins only
- [ ] All isolation tests pass
- [ ] All permission tests pass
- [ ] All engine registry tests pass
- [ ] All token workspace tests pass
- [ ] Total test count: existing 101 + new workspace tests
- [ ] Full battle test: deploy → create workspaces → assign users → ingest → query → verify
```

---

## 4. Test Case Specs (Summary)

| Test File | Cases | What it proves |
|---|---|---|
| test_workspace_isolation.py | ~10 | Data in workspace A is invisible from workspace B. Cross-workspace writes rejected. |
| test_permissions.py | ~20 | Viewer/member/chair/org admin permissions enforced correctly. Archived workspace read-only. |
| test_engine_registry.py | ~7 | Engines created lazily, cached, thread-safe. pyodbc.pooling disabled. |
| test_token_workspace.py | ~5 | Tokens resolve to users with correct memberships and roles. |
| **Total new tests** | **~42** | |
| **Existing tests** | **101** | Must continue to pass. |

---

## 5. Gate Checklists

### Gate 1 (after W1)
```
[ ] App starts without errors (python -m server.src.main --http)
[ ] All 101 existing tests pass (pytest)
[ ] GET /api/health returns 200
[ ] pyodbc.pooling == False (add assertion in test)
[ ] EngineRegistry instantiable, get_engine() returns an engine
[ ] get_db_for(engine) yields a working cursor
[ ] get_db() still works (backward compat)
[ ] get_control_db() works when CONTROL_DB_NAME is set
[ ] WorkspaceContext instantiable with test data
[ ] check_permission() enforces viewer/member/chair/org_admin correctly
[ ] MCP tools still work (manual test: call list_meetings via MCP)
[ ] API endpoints still work (manual test: GET /api/meetings)
```

### Gate 2 (after W2)
```
[ ] All tool functions have (cursor, ctx) as first two params
[ ] No tool function calls get_db() internally
[ ] No inline SQL in api.py
[ ] All API endpoints use Depends(resolve_workspace)
[ ] All MCP tools resolve WorkspaceContext via contextvars
[ ] All MCP tools have optional workspace parameter
[ ] 3 new MCP tools: list_workspaces, switch_workspace, get_current_workspace
[ ] Permission enforcement active: viewer create → 403
[ ] Permission enforcement active: member delete → 403
[ ] Permission enforcement active: chair delete → 200
[ ] Archived workspace write → 403
[ ] All existing tests updated and passing
```

### Gate 3 (after W3)
```
[ ] manage_tokens.py create --user X --workspace Y --role Z → token created
[ ] manage_tokens.py list → shows tokens with workspace memberships
[ ] Token validation returns WorkspaceContext (not just email)
[ ] POST /api/admin/workspaces → creates database + registers
[ ] GET /api/admin/workspaces → lists all workspaces
[ ] POST /api/admin/workspaces/{id}/members → adds member
[ ] Non-admin user → 403 on admin endpoints
[ ] Audit log records operations (check audit_log table)
```

### Gate 4 (after W4)
```
[ ] deploy-new-client.sh creates server + control DB + General workspace DB
[ ] Control DB has 5 tables
[ ] General workspace DB has data tables
[ ] MI has access to both databases
[ ] CONTROL_DB_NAME in container app environment
[ ] migrate-to-workspaces.py upgrades existing deployment
[ ] Existing tokens work after migration
[ ] migrate-all-workspaces.py runs schema on all workspace DBs
[ ] Fireflies transcript routes to correct workspace
[ ] Unroutable transcript → General workspace
```

### Gate 5 (after W5)
```
[ ] Workspace switcher visible in web UI header
[ ] Switching workspace changes data views
[ ] Viewer: no edit/delete buttons visible
[ ] Admin panel: accessible to chair + org admin only
[ ] test_workspace_isolation.py: all pass
[ ] test_permissions.py: all pass
[ ] test_engine_registry.py: all pass
[ ] test_token_workspace.py: all pass
[ ] Total tests: 101 existing + ~42 new = ~143 passing
[ ] Battle test: full end-to-end scenario passes
```

---

## Craig-Dependent Items — Assumed Defaults

> **⚠️ CRAIG REVIEW REQUIRED:** The following two decisions have been assumed to unblock sprint prep. Craig must confirm or override before W3/W4 execution. If Craig's answer differs, the affected prompts (W3 admin API, W4 MI permissions) need updating — changes are localised, not architectural.

### Azure AD Integration → ASSUMED: App Roles

**Default assumption:** App Roles, not Azure AD Groups.

- Define roles in app manifest: `MI.Board.Chair`, `MI.Board.Member`, `MI.Ops.Viewer`, etc.
- Roles appear in JWT `roles` claim — **not subject to 200 group limit**
- Requires Entra ID P1 licensing (confirm Craig's tenant has this)
- Craig assigns roles to users in Entra portal
- Web auth (`authenticate_web`) reads `roles` claim from JWT, maps to WorkspaceContext

**Why this default:** Research found Azure AD groups silently disappear from JWTs at 200+ groups. App Roles avoid this entirely. They're also cleaner — purpose-built for application-level RBAC, not overloaded directory groups.

**If Craig says Groups instead:** Change `authenticate_web` to read `groups` claim, add `groupMembershipClaims: "ApplicationGroup"` to app manifest, implement Graph API overage fallback. ~0.5 day additional work in W3.

**Craig questions:**
1. Does the Entra tenant have P1 licensing? (Required for App Roles assignment)
2. Is Craig comfortable defining App Roles in the MI app registration?
3. Any naming convention preferences for role values?

### Managed Identity Permissions → ASSUMED: FROM EXTERNAL PROVIDER

**Default assumption:** `CREATE USER [app-name] FROM EXTERNAL PROVIDER`, not SID-based.

- Simpler T-SQL, well-documented by Microsoft
- Requires: Entra admin set on SQL Server (Craig already does this) + SQL Server identity has `User.Read.All` Graph permission
- Used in `grant-mi-access.sql` and in the admin API workspace provisioning (W3.4)

**Why this default:** Craig's security layer already sets Entra admin on the SQL Server. `FROM EXTERNAL PROVIDER` is the standard approach in Microsoft's own docs. The SID-based approach is a workaround for environments where Graph permissions are locked down — unlikely in Craig's setup.

**If Craig says SID-based instead:** Change `grant-mi-access.sql` to compute SID from MI client ID (`SELECT CAST(CAST('{client-id}' AS UNIQUEIDENTIFIER) AS VARBINARY(16))`) and use `CREATE USER [app-name] WITH SID = @sid, TYPE = E`. ~0.5 day change in W4.

**Craig questions:**
1. Does the SQL Server's managed identity have `User.Read.All` Graph permission?
2. Any restrictions on `FROM EXTERNAL PROVIDER` in his security policies?

---

*Pre-work package complete. Sprint-ready with assumed defaults. Craig confirmation needed on Azure AD (App Roles) and MI permissions (FROM EXTERNAL PROVIDER) before W3/W4 execution.*

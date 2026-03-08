# DOC5 — Application Architecture

**Meeting Intelligence System**
**Version:** 1.0 — 27 February 2026
**Audience:** Internal / Technical stakeholders
**Owner:** Caleb Lucas, Generation AI

---

## What It Is

A meeting intelligence platform that captures meetings, actions, and decisions from team discussions. Three interfaces: MCP tools for AI assistants (Claude, Copilot), a REST API for the web UI, and the React web UI itself. Single Python container (FastAPI), multi-tenant via workspace databases on Azure SQL.

**Stack:** Python 3.12 (FastAPI, FastMCP, SQLAlchemy, Pydantic), React 18 (Vite, MSAL), Azure SQL Server, Docker.

---

## Data Model

### Workspace Database (one per workspace)

Three core entities with cascade delete from Meeting → Action and Meeting → Decision.

**Meeting**

| Field | Type | Notes |
|-------|------|-------|
| MeetingId | INT PK | Auto-increment |
| Title | NVARCHAR(255) | Required |
| MeetingDate | DATETIME2 | Required |
| RawTranscript | NVARCHAR(MAX) | Nullable |
| Summary | NVARCHAR(MAX) | Markdown format |
| Attendees | NVARCHAR(MAX) | Comma-separated names |
| Source | NVARCHAR(50) | `Manual` or `Fireflies` |
| SourceMeetingId | NVARCHAR(255) | For deduplication (Fireflies ID) |
| Tags | NVARCHAR(MAX) | Comma-separated, lowercase |
| CreatedAt, CreatedBy, UpdatedAt, UpdatedBy | | Audit trail |

**Action**

| Field | Type | Notes |
|-------|------|-------|
| ActionId | INT PK | Auto-increment |
| MeetingId | INT FK | Nullable (standalone actions allowed) |
| ActionText | NVARCHAR(MAX) | Required |
| Owner | NVARCHAR(128) | Required |
| DueDate | DATE | Nullable, ISO 8601 |
| Status | NVARCHAR(20) | `Open` / `Complete` / `Parked` |
| Notes | NVARCHAR(MAX) | Nullable |
| CreatedAt, CreatedBy, UpdatedAt, UpdatedBy | | Audit trail |

**Decision**

| Field | Type | Notes |
|-------|------|-------|
| DecisionId | INT PK | Auto-increment |
| MeetingId | INT FK | Required |
| DecisionText | NVARCHAR(MAX) | Required |
| Context | NVARCHAR(MAX) | Reasoning behind the decision |
| CreatedAt, CreatedBy | | Audit trail |

### Control Database (one per client)

Five tables managing users, workspaces, tokens, and audit.

**workspaces** — `id`, `name` (slug, unique), `display_name`, `db_name` (actual database name), `is_default`, `is_archived`, `created_at`, `created_by`, `archived_at`

**users** — `id`, `email` (unique), `display_name`, `is_org_admin` (boolean), `default_workspace_id` (FK), `created_at`, `created_by`

**workspace_members** — `id`, `user_id` (FK), `workspace_id` (FK), `role` (`viewer` | `member` | `chair`), `added_at`, `added_by`. Unique constraint on (user_id, workspace_id).

**tokens** — `id`, `token_hash` (SHA256, unique), `user_id` (FK), `client_name`, `is_active`, `created_at`, `created_by`, `expires_at`, `revoked_at`, `notes`

**audit_log** — `id`, `user_email`, `workspace_id`, `workspace_name`, `operation` (`read` | `create` | `update` | `delete`), `entity_type` (`meeting` | `action` | `decision` | `workspace` | `member` | `token`), `entity_id`, `detail`, `timestamp`, `auth_method` (`mcp` | `web` | `admin`)

---

## Multi-Tenancy

Two-tier isolation model:

1. **Control Database** (one per customer) — users, workspaces, tokens, audit. Shared across all workspaces for that client.
2. **Workspace Databases** (N per customer) — one database per workspace. Meeting, Action, and Decision data is fully isolated at the database level.

All databases live on the same Azure SQL Server, connected via managed identity.

**Request resolution flow:**

1. Authenticate (validate MCP token or Azure AD JWT) → get user email
2. Query control DB → get user's workspace memberships, roles, org_admin flag
3. Resolve active workspace: explicit `X-Workspace-ID` header > user's default > org default > first membership
4. Get database connection from EngineRegistry (lazy pool per database)
5. Execute operation on that workspace's database

**EngineRegistry** — Thread-safe connection pool manager. One SQLAlchemy engine per database, lazy-created on first access. Pool size 3, max overflow 1 per database (total max 4 connections per workspace). Azure AD token auth via ODBC Driver 18. All engines disposed on app shutdown.

**Workspace switching** — MCP `switch_workspace` tool stores preference in an in-memory dict keyed by user email. Persists across stateless HTTP requests for the same user session. Web UI sends `X-Workspace-ID` header on every request.

---

## MCP Tools (23)

All registered via FastMCP framework. Transport: Streamable HTTP (endpoint: `/mcp`).

### Meetings (6)

| Tool | Type | What it does |
|------|------|-------------|
| `list_meetings` | Read | List recent meetings. Params: limit, days_back, attendee, tag |
| `get_meeting` | Read | Full meeting detail with transcript, summary, attendees |
| `search_meetings` | Read | Full-text search on title and transcript |
| `create_meeting` | Write | Create meeting record. Supports Fireflies source dedup |
| `update_meeting` | Write | Modify title, summary, attendees, transcript, tags |
| `delete_meeting` | Destructive | Delete meeting + cascade delete linked actions/decisions |

### Actions (8)

| Tool | Type | What it does |
|------|------|-------------|
| `list_actions` | Read | List with filters: status, owner, meeting_id. Sorted by due date |
| `get_action` | Read | Full action detail with linked meeting |
| `search_actions` | Read | Full-text search on action text, owner, notes |
| `create_action` | Write | Create action item. Due date in ISO 8601 |
| `update_action` | Write | Modify text, owner, due date, notes. Cannot change status |
| `complete_action` | Write | Mark complete. Idempotent |
| `park_action` | Write | Put on hold |
| `delete_action` | Destructive | Permanently delete |

### Decisions (5)

| Tool | Type | What it does |
|------|------|-------------|
| `list_decisions` | Read | List by meeting, sorted by creation date desc |
| `get_decision` | Read | Full detail with context and creator |
| `search_decisions` | Read | Full-text search on decision text and context |
| `create_decision` | Write | Record decision linked to a meeting |
| `delete_decision` | Destructive | Permanently delete |

### Workspaces (3)

| Tool | Type | What it does |
|------|------|-------------|
| `list_workspaces` | Read | User's workspace memberships with roles |
| `get_current_workspace` | Read | Active workspace details and permissions |
| `switch_workspace` | Write | Change active workspace for subsequent calls |

### Schema (1)

| Tool | Type | What it does |
|------|------|-------------|
| `get_schema` | Read | Field definitions, types, constraints for all entities |

---

## REST API

~30 endpoints serving the web UI. Most mounted at `/api/`.

### Authentication & Profile

- `GET /api/me` — User profile, workspace memberships, permissions

### Meetings

- `GET /api/meetings` — List (limit, offset, days_back)
- `GET /api/meetings/search` — Search (query, limit)
- `GET /api/meetings/{id}` — Detail with linked actions/decisions
- `PATCH /api/meetings/{id}` — Update
- `DELETE /api/meetings/{id}` — Delete (cascades)

### Actions

- `GET /api/actions` — List (status, owner, meeting_id, limit, offset)
- `GET /api/actions/{id}` — Detail
- `POST /api/actions` — Create
- `PATCH /api/actions/{id}` — Update
- `PATCH /api/actions/{id}/status` — Change status
- `GET /api/actions/owners` — Distinct owner list (for filter dropdown)
- `DELETE /api/actions/{id}` — Delete

### Decisions

- `GET /api/decisions` — List (meeting_id, limit, offset)
- `GET /api/decisions/{id}` — Detail
- `POST /api/decisions` — Create
- `DELETE /api/decisions/{id}` — Delete

### Token Management (self-service)

- `GET /api/me/tokens` — List user's tokens (metadata only, no plaintext)
- `POST /api/me/tokens` — Create PAT (plaintext shown once, then SHA256 stored)
- `DELETE /api/me/tokens/{id}` — Revoke

### Workspace Admin (org_admin / chair)

Mounted at `/api/admin/`.

- `GET /api/admin/workspaces` — List all workspaces
- `POST /api/admin/workspaces` — Create workspace (org_admin)
- `PATCH /api/admin/workspaces/{id}` — Archive/unarchive (org_admin)
- `GET /api/admin/workspaces/{id}/members` — List members
- `POST /api/admin/workspaces/{id}/members` — Add member (chair)
- `PATCH /api/admin/workspaces/{id}/members/{userId}` — Change role (chair)
- `DELETE /api/admin/workspaces/{id}/members/{userId}` — Remove member (chair)

### Health & Schema

- `GET /health/ready` — Readiness probe (no auth)
- `GET /health/live` — Liveness probe (no auth)
- `GET /api/health` — Basic health check (no auth)
- `GET /api/schema` — Entity field definitions (no auth)

### Audit

- `GET /api/admin/workspaces/{id}/audit` — Workspace audit log (org_admin / chair)

---

## Middleware Chain

Request lifecycle from ingress to handler:

1. **Payload Size Limit** — 1 MB max. Rejects at ASGI level → 413
2. **Rate Limiting** — Sliding window. MCP: 120/min per token (keyed by SHA256 of auth header). API: 60/min per IP. Exempt: `/health` → 429
3. **Request Logging** — Method, path, status on every request. Debug level.
4. **CORS** — Allowed origins from config. Credentials allowed. Methods: GET, POST, DELETE, OPTIONS, PATCH.
5. **Authentication** — Bearer token (MCP PAT or Azure AD JWT). Stores email on `request.state`.
6. **Workspace Resolution** — Queries control DB for memberships, resolves active workspace.
7. **RBAC Check** — Role-based permission enforcement before data access.
8. **Input Validation** — Pydantic schemas. HTML stripping, null byte removal, date validation.
9. **Handler** — Tool function or API endpoint executes against workspace database.
10. **Audit Logging** — Async fire-and-forget to control DB `audit_log` table after write operations.

---

## RBAC

Four roles plus an org-level admin flag:

| Permission | viewer | member | chair | org_admin |
|-----------|--------|--------|-------|-----------|
| Read | ✓ | ✓ | ✓ | ✓ |
| Create | | ✓ | ✓ | ✓ |
| Update (own) | | ✓ | ✓ | ✓ |
| Update (any) | | | ✓ | ✓ |
| Delete | | | ✓ | ✓ |
| Manage members | | | ✓ | ✓ |
| Manage workspaces | | | | ✓ |

Archived workspaces are read-only for all roles.

---

## Web UI

React 18 + Vite. Azure AD login via MSAL. 9 pages:

| Page | Route | What it does |
|------|-------|-------------|
| Meetings List | `/meetings` | List, search, filter by date/attendee/tag. Pagination. |
| Meeting Detail | `/meetings/:id` | Full view with linked actions and decisions |
| Actions List | `/actions` | List, filter by status/owner, inline status changes, create form |
| Action Detail | `/actions/:id` | Full action view |
| Decisions List | `/decisions` | List with pagination |
| Decision Detail | `/decisions/:id` | Full decision view |
| Workspace Admin | `/admin/workspaces` | Workspace CRUD, member management. org_admin only. |
| Settings | `/settings` | User profile, PAT management (create/list/revoke) |
| Login | `/login` | Azure AD redirect |

**Key components:**

- **Layout** — App shell with top navbar, workspace switcher dropdown, user profile menu, workspace error banner
- **WorkspaceSwitcher** — Dropdown that sets `X-Workspace-ID` header on all API calls
- **WorkspaceContext** — React context for active workspace, permissions, user profile. Handles 403 errors by auto-switching to available workspace or showing access revoked message. Triggers refetch on workspace switch via `workspaceVersion` counter.
- **api.js** — HTTP client with MSAL token provider, workspace header injection, 401 (clear MSAL cache + redirect to login), 403 (throw AccessDeniedError for workspace recovery)

---

## Input Validation

All inputs validated via Pydantic schemas (`server/src/schemas.py`):

- HTML tag stripping (XSS prevention)
- Null byte removal
- ISO 8601 date validation
- Comma-separated list sanitisation
- Markdown format enforcement on summaries (500+ chars must contain markdown)
- Field length constraints per entity schema

Shared between MCP tools and REST API via `get_schema` endpoint — single source of truth.

---

## Error Handling

- **401 Unauthorized (web UI)** — Clear MSAL cache and redirect to login on ANY token acquisition failure. Prevents stuck-on-401 state when access or refresh tokens expire. (Action #1)
- **403 Forbidden (web UI)** — Catch AccessDeniedError, check available workspaces. If user has other workspaces, auto-switch to first available with warning banner. If no workspaces, show "access revoked, contact admin" message. (Action #2)
- **Transient Azure SQL errors** — Detected by error code (40613, 40197, 49919, etc.). Exponential backoff retry: 0.5s → 1s → 2s → max 10s.
- **Fail-closed auth** — Control DB unavailable → 503 (not silent admin escalation).
- **Tool errors** — Return error dict to MCP client, never stack traces.
- **Structured logging** — JSON format, compatible with Azure Application Insights. Redacts token prefixes and partial IDs.

---

## Application Startup

1. Initialise logging (structured JSON)
2. Create MCP streamable HTTP app (FastMCP)
3. Initialise EngineRegistry (lazy database connections)
4. Set up FastAPI lifespan (async context manager)
5. Add middleware stack (payload limit → rate limit → logging → CORS)
6. Mount MCP transport at `/mcp`
7. Mount REST API at `/api/` + admin router at `/api/admin/`
8. Mount static assets (React build) at `/`
9. Listen on port 8000

Shutdown: dispose all engines, MCP session cleanup.

---

*For infrastructure architecture, see DOC2. For deployment procedures, see DOC3. For operational procedures, see DOC4.*

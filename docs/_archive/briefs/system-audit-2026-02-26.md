# Meeting Intelligence — Full System Audit

**Date:** 2026-02-26
**Purpose:** Complete inventory of the system for v2 rebuild evaluation
**Auditor:** Claude Code (5 parallel audit streams)

---

## 1. What We Built — Feature Inventory

### 1.1 MCP Tools (23 total)

| # | Tool | Category | RBAC | Audit | Notes |
|---|------|----------|------|-------|-------|
| 1 | list_meetings | Meetings | All | No | Filters: attendee, tag, days_back, limit |
| 2 | get_meeting | Meetings | All | No | Returns full meeting incl transcript |
| 3 | search_meetings | Meetings | All | No | LIKE search on title/summary/transcript with snippet |
| 4 | create_meeting | Meetings | Member+ | Yes | Markdown validation if summary >500 chars |
| 5 | update_meeting | Meetings | Member(own)/Chair | Yes | Cannot update meeting_date (immutable) |
| 6 | delete_meeting | Meetings | Chair | Yes | Cascades to actions + decisions (app code, no FK cascade) |
| 7 | list_actions | Actions | All | No | Filters: status, owner, meeting_id |
| 8 | get_action | Actions | All | No | |
| 9 | search_actions | Actions | All | No | LIKE search on text/owner/notes |
| 10 | create_action | Actions | Member+ | Yes | Owner is free-form text |
| 11 | update_action | Actions | Member(own)/Chair | Yes | Cannot change status (use complete/park) |
| 12 | complete_action | Actions | Member(own)/Chair | Yes | Idempotent |
| 13 | park_action | Actions | Member(own)/Chair | Yes | No transition validation |
| 14 | delete_action | Actions | Chair | Yes | |
| 15 | list_decisions | Decisions | All | No | JOIN with Meeting for title |
| 16 | get_decision | Decisions | All | No | Immutable — no update tool |
| 17 | search_decisions | Decisions | All | No | LIKE search on text/context |
| 18 | create_decision | Decisions | Member+ | Yes | Requires meeting_id (tight coupling) |
| 19 | delete_decision | Decisions | Chair | Yes | |
| 20 | list_workspaces | Workspace | All | No | From cached memberships, no DB query |
| 21 | get_current_workspace | Workspace | All | No | Shows role, permissions, db_name |
| 22 | switch_workspace | Workspace | All | No | In-memory override, keyed by email |
| 23 | get_schema | Utility | All | No | Field definitions, types, examples |

**Gaps found:**
- `reopen_action` exists in tools/actions.py but is NOT exposed as MCP tool
- `list_actions` docstring says "returns Open only" but code returns all statuses
- No confirmation step on destructive operations (delete cascades silently)
- No soft delete anywhere

### 1.2 REST API Endpoints (16 total)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | /api/me | User profile + workspace memberships + permissions | Azure AD / Token |
| GET | /api/meetings | List meetings (paginated) | Protected |
| GET | /api/meetings/search | Search meetings by keyword | Protected |
| GET | /api/meetings/{id} | Meeting detail + linked actions/decisions | Protected |
| DELETE | /api/meetings/{id} | Delete meeting (cascade) | Protected |
| GET | /api/actions | List actions (filterable) | Protected |
| GET | /api/actions/owners | Distinct owner list for filter dropdown | Protected |
| GET | /api/actions/{id} | Action detail | Protected |
| PATCH | /api/actions/{id}/status | Update status (Open/Complete/Parked) | Protected |
| DELETE | /api/actions/{id} | Delete action | Protected |
| GET | /api/decisions | List decisions (filterable by meeting) | Protected |
| GET | /api/decisions/{id} | Decision detail | Protected |
| DELETE | /api/decisions/{id} | Delete decision | Protected |
| GET | /api/schema | Field definitions for all entities | Protected |
| GET | /api/health | Health check | Public |
| GET | /health/ready | Readiness probe (DB connection) | Public |
| GET | /health/live | Liveness probe (process alive) | Public |

### 1.3 Admin API Endpoints (7 total)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | /admin/workspaces | Create workspace (creates DB + schema + MI access) | Org Admin |
| GET | /admin/workspaces | List workspaces | Org Admin (all) / Others (own) |
| PATCH | /admin/workspaces/{id} | Archive/unarchive workspace | Org Admin |
| GET | /admin/workspaces/{id}/audit | View audit log | Org Admin / Chair |
| POST | /admin/workspaces/{id}/members | Add member | Org Admin / Chair |
| GET | /admin/workspaces/{id}/members | List members | Org Admin / Chair |
| PATCH | /admin/workspaces/{id}/members/{uid} | Change role | Org Admin / Chair |
| DELETE | /admin/workspaces/{id}/members/{uid} | Remove member | Org Admin / Chair |

### 1.4 OAuth 2.1 Endpoints (6 total)

| Method | Path | Purpose | RFC |
|--------|------|---------|-----|
| GET | /.well-known/oauth-protected-resource | Resource metadata | RFC 9728 |
| GET | /.well-known/oauth-authorization-server | Auth server metadata | RFC 8414 |
| POST | /oauth/register | Dynamic client registration | RFC 7591 |
| GET/POST | /oauth/authorize | Consent page + auth code grant | RFC 6749 |
| POST | /oauth/token | Token exchange + refresh | RFC 6749 |
| POST | /oauth/revoke | Token revocation | RFC 7009 |

### 1.5 Web UI Pages (7 routes)

| Route | Page | Features | Write Actions |
|-------|------|----------|---------------|
| /login | Login | Azure AD sign-in | None |
| /meetings | MeetingsList | List, search, pagination | None |
| /meetings/:id | MeetingDetail | Full detail, linked items, markdown rendering | Delete (chair) |
| /actions | ActionsList | List, filter (status/owner), sort, pagination | Status update (member+) |
| /actions/:id | ActionDetail | Full detail, status buttons | Status update, Delete (chair) |
| /decisions | DecisionsList | List, filter by meeting, pagination | None |
| /decisions/:id | DecisionDetail | Full detail with context | Delete (chair) |
| /admin/workspaces | WorkspaceAdmin | Create workspace, manage members, archive | Full CRUD (chair/admin) |

**What the web UI CANNOT do:**
- Create meetings, actions, or decisions (no forms)
- Edit meeting/action/decision content (read-only)
- Search actions or decisions
- Filter by attendee
- Auto-refresh or poll for updates
- Re-fetch on workspace switch (requires hard refresh)

---

## 2. Authentication — Three Flows

### 2.1 MCP Token Auth (Claude, Copilot)
- Token extracted from: path `/mcp/{token}`, query `?token=`, header `X-API-Key` or `Bearer`
- SHA256(plaintext) → lookup in control DB `tokens` table
- 5-min in-memory cache (max 1000 entries)
- Pre-caches WorkspaceContext to avoid 2nd DB hit
- Identity: user email (e.g., `caleb.lucas@generationai.co.nz`)

### 2.2 Azure AD Auth (Web UI)
- MSAL + fastapi-azure-auth SingleTenantAzureAuthorizationCodeBearer
- Token claims: preferred_username > upn > email
- v2 tokens required (accessTokenAcceptedVersion: 2)
- Legacy mode: ALLOWED_USERS whitelist check
- Workspace mode: control DB memberships are sole access gate

### 2.3 OAuth 2.1 (ChatGPT)
- Dynamic Client Registration + PKCE + refresh token rotation
- Consent page requires existing MCP token (token-gated)
- JWT access tokens (1hr) + refresh tokens (30d, single-use with family tracking)
- Identity: `oauth:{client_id}` — has no workspace memberships by default
- **Currently broken for workspace mode** (oauth identity not in control DB)

### Legacy Fallback (CRITICAL)
- When control DB not configured: `make_legacy_context()` grants `is_org_admin=True` + `role=chair`
- 7 code paths trigger fallback (missing config, DB failure, zero memberships, etc.)
- **Fail-open anti-pattern** — any transient DB issue = all users become admin

---

## 3. Database Architecture

### 3.1 Schema — Workspace Databases (per workspace)

| Table | Columns | Indexes | FK |
|-------|---------|---------|-----|
| Meeting | MeetingId (PK), Title, MeetingDate, RawTranscript, Summary, Attendees, Source, SourceMeetingId, Tags, CreatedAt, CreatedBy, UpdatedAt, UpdatedBy | MeetingDate DESC, SourceMeetingId | None |
| Action | ActionId (PK), MeetingId, ActionText, Owner, DueDate, Status, Notes, CreatedAt, CreatedBy, UpdatedAt, UpdatedBy | Status, Owner, DueDate, MeetingId | Meeting (optional) |
| Decision | DecisionId (PK), MeetingId, DecisionText, Context, CreatedAt, CreatedBy | MeetingId | Meeting (required) |
| ClientToken | TokenId (PK), TokenHash, ClientName, ClientEmail, IsActive, ExpiresAt, CreatedAt, CreatedBy, LastUsedAt, Notes | TokenHash (filtered) | None |
| OAuthClient | ClientId (PK), ClientName, ClientSecret, RedirectUris, GrantTypes, ResponseTypes, Scope, TokenEndpointAuthMethod, CreatedAt, IsActive | None | None |
| RefreshTokenUsage | TokenHash (PK), FamilyId, ClientId, ConsumedAt | ConsumedAt, FamilyId | None |

### 3.2 Schema — Control Database (per environment)

| Table | Columns | Purpose |
|-------|---------|---------|
| workspaces | id, name, display_name, db_name, is_default, is_archived, created_at, created_by, archived_at | Workspace registry |
| users | id, email, display_name, is_org_admin, default_workspace_id, created_at, created_by | User registry |
| workspace_members | id, user_id, workspace_id, role, added_at, added_by | RBAC membership |
| tokens | id, token_hash, user_id, client_name, is_active, created_at, created_by, expires_at, revoked_at, notes | MCP token registry |
| audit_log | id, user_email, workspace_id, workspace_name, operation, entity_type, entity_id, detail, timestamp, auth_method | Audit trail |

### 3.3 Connection Architecture
- **EngineRegistry**: Thread-safe lazy engine cache, one SQLAlchemy engine per database
- **Pool**: QueuePool (size=3, overflow=1, recycle=30min, pre_ping=True)
- **Auth**: Azure Managed Identity (DefaultAzureCredential) — no passwords
- **Retry**: 17 transient SQL error codes, exponential backoff (3 retries, 0.5-2s)

---

## 4. Infrastructure

### 4.1 Bicep Modules (6)

| Module | Resources Created |
|--------|-------------------|
| sql.bicep | SQL Server + control DB + general DB |
| keyvault.bicep | Key Vault + JWT_SECRET + App Insights secret |
| container-app.bicep | Container App + Environment + registry config |
| identity.bicep | Key Vault Secrets User + ACR Pull role assignments |
| monitoring.bicep | Log Analytics + Application Insights |
| alerts.bicep | 7 alert rules (5xx, latency, CPU, memory, restarts, replica-zero, auth failures) |

### 4.2 Deploy Scripts

| Script | Purpose | When |
|--------|---------|------|
| deploy-new-client.sh | Full greenfield (6 phases: App Reg → Bicep → DB → Token → CORS → Health) | New client |
| deploy-bicep.sh | Core Bicep deploy + RBAC + health check | Image updates |
| deploy-all.sh | Multi-env canary rollout (internal first, then clients) | Batch deploy |
| audit.sh | Pre-deploy vulnerability scan (pip-audit, npm audit, trivy) | Before deploy |

### 4.3 Operational Scripts

| Script | Purpose |
|--------|---------|
| manage_tokens.py | Token/user/membership CRUD via CLI |
| migrate.py | SQL migration runner with checksum tracking |
| migrate-data-cross-server.py | Cross-server data migration (preserves IDs) |
| migrate-to-workspaces.py | Upgrade single-DB deployment to workspace mode |
| battle-test.py | 60+ automated test cases against live environment |

---

## 5. Test Coverage

### 5.1 What's Tested (229 tests, all passing)

| Area | Tests | Coverage |
|------|-------|----------|
| Pydantic validation | 60+ | Field limits, dates, status values, HTML stripping, markdown |
| RBAC permissions | 40+ | Viewer/member/chair/org_admin, archived workspace blocks |
| Workspace isolation | 25+ | Cross-workspace access denied, context immutability |
| Token auth | 20+ | SHA256 hashing, workspace resolution, memberships |
| Admin API | 30+ | Workspace CRUD, member management, slug validation |
| Schema endpoint | 15+ | Entity definitions, field metadata |
| Engine registry | 7 | Lazy creation, cache hits, thread safety |
| Audit logging | 9 | Insert, truncation, exception swallowing |

### 5.2 What's NOT Tested (Gaps)

| Gap | Impact |
|-----|--------|
| Integration tests (E2E workflows) | Critical — no create→query→update→delete flows |
| MCP tool handlers (23 tools) | High — validation tested, tool orchestration not |
| REST API endpoints (16 endpoints) | High — HTTP status codes, error responses untested |
| OAuth 2.1 flow | Medium — DCR, token exchange, refresh rotation untested |
| Rate limiting | Medium — 429 responses, Retry-After headers |
| Search functionality | Medium — keyword matching, snippet extraction |
| Azure SQL retry logic | Medium — transient failure handling |
| CI/CD pipeline | N/A — doesn't exist |

---

## 6. Gotchas — Classified

### 6.1 Architectural (Would require design change in v2)

| Gotcha | Severity | v2 Implication |
|--------|----------|----------------|
| `make_legacy_context()` fail-open — grants admin to all on DB failure | CRITICAL | Remove legacy mode entirely |
| Three separate auth flows producing different identity models | HIGH | Unify to single token-based auth |
| Per-workspace databases multiply operations (migrations, tables, costs) | HIGH | Schema-based isolation instead |
| OAuth identity `oauth:{client_id}` has no workspace memberships | HIGH | Map OAuth to user email or auto-create membership |
| External Azure AD accounts fail (single-tenant) | MEDIUM | Multi-tenant auth or B2B guest model |
| No soft delete anywhere — hard deletes are permanent | MEDIUM | Add is_deleted + deleted_at on all entities |
| Python import binding copies None at import time | CRITICAL | Module architecture must avoid mutable module-level state |

### 6.2 Operational (Deployment/DevOps knowledge to preserve)

| Gotcha | Notes |
|--------|-------|
| Key Vault RBAC takes 5-10 min to propagate | Deploy script waits 180s then forces new revision |
| First Bicep deploy fails at containerapp (expected) | ACR Pull not yet assigned; retry after assigning |
| Pre-Bicep envs (team/demo) can't use full Bicep deploy | Use `az containerapp update --image` for image-only |
| Docker build needs all 4 VITE build args | React compiles with placeholders otherwise |
| Azure AD accessTokenAcceptedVersion defaults to v1 | Must set to v2 on every new App Registration |
| Container restart needed after MI DB user creation | Readiness probe caches "no access" state |
| YAML update wipes all env vars | Never use `az containerapp update --yaml` |
| SPA redirect URIs need both base URL and /auth/callback | MSAL uses origin, not path |
| `dbmanager` role on master needed for workspace creation | Granted by deploy script Step 2a |
| Deleting workspace DB breaks legacy token fallback | `AZURE_SQL_DATABASE` must point to DB with ClientToken table |

### 6.3 Implementation (Bugs/patterns to avoid)

| Gotcha | Fix |
|--------|-----|
| `from .module import mutable_var` copies None | Use `from . import module; module.var` |
| `uv run pytest` fails | Use `uv run python -m pytest` |
| `.bicepparam` with `using` rejects CLI `--parameters` | Use `readEnvironmentVariable()` |
| Route `{path:path}` with arg `_path` causes JSON error | Names must match exactly |
| Git same tag = no new revision | Use `$(date +%Y%m%d%H%M%S)` |
| MI Object ID vs Client ID for DB SID | Azure SQL needs Application (Client) ID |

---

## 7. Ideas Bucket + Known Gaps → v2 Requirements

### Must-Have (blocking or high-impact)

| Item | Effort | Why |
|------|--------|-----|
| Single auth model (token-only with self-service UI) | 2-3 days | Eliminates 3-flow complexity, enables ChatGPT users |
| Soft delete on all entities | 0.5 day | No recovery from accidental deletion today |
| Schema-based isolation (not per-DB) | 1 day | Simplifies migrations, reduces costs, eliminates table-creation incidents |
| Drop legacy mode entirely | 1 day | Source of most critical bugs (fail-open admin, dual code paths) |
| CI/CD pipeline | 0.5 day | 229 tests never run automatically |
| Full CRUD in web UI | 2-3 days | Currently read-only for creation |
| Confirmation on destructive MCP ops | 0.5 day | delete_meeting cascades silently |
| Chair-only delete | 0.5 day | Members can delete anything today |

### Nice-to-Have (UX/feature)

| Item | Effort | Why |
|------|--------|-----|
| Workspace switch re-fetches data | 1 hr | Currently requires hard refresh |
| Auto-refresh / polling | 0.5 day | Content goes stale |
| Expose reopen_action as MCP tool | 15 min | Function exists but not wired up |
| Email notifications for overdue actions | 1-2 days | No notification system |
| PostgreSQL instead of Azure SQL | 1 day | Cheaper, simpler, no ODBC driver headaches |

---

## 8. What Users Actually Use

### Active Usage (confirmed)
- MCP tools via Claude (primary interface for Caleb + Mark)
- Web UI for viewing meetings/actions/decisions
- Action status updates via web UI
- Workspace switching (MCP + web UI)
- Admin API for workspace/member management

### Built but Unused/Broken
- OAuth 2.1 for ChatGPT (identity model broken for workspace mode)
- `meetingsApi.search()` defined in web API but not wired to any UI component
- `ExpandableText` component (leftover, unused)
- `MCP_AUTH_TOKENS` env var (legacy, only for migration command)
- Attendee filtering in web UI (MCP only)
- `reopen_action` function (not exposed as MCP tool)

### Environments

| Env | Purpose | Status | Scale |
|-----|---------|--------|-------|
| mi-genai | Primary (P7 workspaces) | Active | 0 (scale-to-zero) |
| mi-marshall | Client (John Marshall) | Active | 0 (scale-to-zero) |
| mi-testing-instance | Client demos (Mark) | Active | 1 (always-on) |
| meeting-intelligence-team | Old internal | Legacy — data migrated | 0 |
| meeting-intelligence | Old demo | Legacy — data migrated | 0 |

---

## 9. Summary

**Total surface area:**
- 23 MCP tools
- 16 REST endpoints
- 8 Admin endpoints
- 6 OAuth endpoints
- 7 Web UI routes
- 3 auth flows
- 6 Bicep modules
- 10 database tables (3 workspace + 5 control + 2 migration)
- 229 tests
- 38 documented gotchas
- 5 deploy/operational scripts

**What works well:** MCP tools, workspace isolation, RBAC model, Bicep IaC, deploy automation, audit logging, security hardening

**What causes pain:** Three auth flows, legacy fallback, per-workspace databases, no soft delete, no CI/CD, web UI is read-only, no auto-refresh

**v2 rebuild estimate:** ~10-12 focused days to rewrite with architectural fixes. See Section 7 for prioritized requirements.

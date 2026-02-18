# Meeting Intelligence System - Agent Context

**Last Updated:** 2026-02-12
**Project Status:** Phase 3 IN PROGRESS — D workstream complete
**Owner:** Caleb Lucas

---

## What This Is

A meeting management system that captures meetings, actions, and decisions from team discussions. Integrates with Claude via MCP (Model Context Protocol) so Claude can directly query and update meeting data. Also provides a React web UI for manual access. Built for Generation AI internal use.

---

## Quick Start

```bash
# Server (Python)
cd server
uv sync
uv run python -m src.main --http  # Run on :8000

# Web (React)
cd web
npm install
npm run dev  # Run on :5173

# Deploy
./infra/deploy-bicep.sh marshall  # or team/demo
```

**Required environment variables (in `.env.deploy`):**
- `AZURE_SQL_SERVER` — Azure SQL server hostname
- `AZURE_SQL_DATABASE` — Database name
- `MCP_AUTH_TOKENS` — (Legacy) JSON map of token hashes to emails. New deployments use DB-backed `ClientToken` table instead.
- `ALLOWED_USERS` — Comma-separated emails for web UI access
- `CORS_ORIGINS` — Allowed CORS origins
- `JWT_SECRET` — Secret for OAuth JWT tokens
- `JWT_SECRET_PREVIOUS` — (Optional) Previous JWT secret for dual-key rotation during secret rotation window
- `OAUTH_BASE_URL` — Base URL for OAuth endpoints (e.g., team instance URL)
- `VITE_*` — Frontend config (client ID, tenant, API URL)

---

## Architecture

FastAPI server handles both REST API (for web UI) and MCP/SSE (for Claude). Single container deployed to Azure Container Apps. Database is Azure SQL with managed identity auth.

```
server/src/
├── main.py          — Entry point (--http for web, stdio for MCP)
├── api.py           — REST API endpoints for web UI
├── mcp_server.py    — MCP tool definitions and handlers
├── config.py        — Environment configuration (pydantic-settings)
├── database.py      — Azure SQL connection (managed identity)
└── tools/           — Business logic (meetings.py, actions.py, decisions.py)

web/src/
├── App.jsx          — React router and auth setup
├── pages/           — MeetingsList, ActionsList, DecisionsList, detail pages
└── components/      — Shared components
```

---

## Key Files

| File | Purpose |
|------|---------|
| `server/src/mcp_server.py` | MCP tool definitions - what Claude can do |
| `server/src/oauth.py` | OAuth 2.1 endpoints for ChatGPT MCP support |
| `server/src/tools/meetings.py` | Meeting CRUD + delete (cascades to actions/decisions) |
| `server/src/config.py` | All environment variable handling |
| `server/src/database.py` | Azure SQL connection with managed identity |
| `deploy.sh` | Legacy deployment script (team/demo) |
| `infra/deploy-bicep.sh` | Bicep deployment script (new environments) |
| `infra/parameters/*.bicepparam` | Per-environment Bicep parameters (committed to git) |
| `server/scripts/manage_tokens.py` | CLI for creating/revoking/rotating client tokens |
| `.env.deploy` | Secrets (not in git) |
| `schema.sql` | Database schema definition |
| `server/migrations/002_client_tokens.sql` | ClientToken + OAuthClient table migration |
| `server/migrations/003_refresh_token_usage.sql` | Refresh token usage tracking migration |
| `server/scripts/migrate.py` | Multi-database migration runner |
| `infra/audit.sh` | Pre-deploy vulnerability scanning (pip-audit + npm audit + trivy) |
| `infra/deploy-all.sh` | Multi-client staged deployment script |

---

## Patterns & Conventions

- **Error responses**: All DB operations return `{"error": True, "code": "...", "message": "..."}` on failure
- **Dates**: ISO 8601 format everywhere
- **Status values**: "Open", "Complete", "Parked" (exact strings)
- **Tags**: Comma-separated lowercase strings (e.g., "planning, engineering")
- **Attendees**: Comma-separated email addresses
- **Auth tokens (new — DB-backed)**: Client receives a plaintext token. Middleware hashes it once with SHA256 and looks up the hash in `ClientToken` table. DB stores `SHA256(plaintext)` — single hash. The old `MCP_AUTH_TOKENS` env var pattern (hash IS the token) is legacy and only used by the `migrate` command.
- **Naming conventions**: Container Apps are `mi-${environmentName}`, resource groups are `meeting-intelligence-${environmentName}-rg`, images are `mi-${environmentName}:<tag>`
- **Managed Identity**: DB auth uses Azure MI SID based on App Registration's Application (Client) ID

---

## What's Been Tried & Failed

| Approach | Why It Failed | Date |
|----------|---------------|------|
| Using MI Object ID for DB SID | Azure SQL needs Application (Client) ID, not Object ID | 2026-02-01 |
| Plaintext MCP tokens | System expects hash as token; hash maps to email in config | 2026-02-02 |
| Git commit tag for deploys | Same tag = no new revision; need unique tag per deploy | 2026-02-03 |
| FastAPI route param name mismatch | Route `{path:path}` with function arg `_path` - FastAPI interprets as query param, causing JSON error on page refresh. Names must match. | 2026-02-05 |
| YAML update for health probes | `az containerapp update --yaml` wipes ALL env vars. Symptom: 401 errors, double-slash in OpenID config URL. Fix: configure probes once via Portal, not in deploy.sh. | 2026-02-05 |
| `.bicepparam` with `using` + CLI `--parameters` | Bicep files with a `using` directive reject CLI `--parameters` overrides. Use `readEnvironmentVariable()` in the `.bicepparam` file for dynamic/secret values instead. | 2026-02-10 |
| Bicep ACR Pull role assignment | `container-app.bicep` uses `identity: 'system'` for ACR registry config, but this does NOT create an ACR Pull role assignment. Must manually assign AcrPull to the managed identity principal after first deploy. | 2026-02-10 |
| Bicep identity module on redeploy | `identity.bicep` assigns Key Vault Secrets User role. If already assigned (e.g., manually), redeploy fails with `RoleAssignmentExists`. Benign — other modules still succeed. | 2026-02-10 |
| Container App readiness after DB user creation | Readiness probe caches "no DB access" state. After creating the managed identity DB user, must restart the Container App revision for it to pick up the new permissions. | 2026-02-10 |
| `--spa-redirect-uris` on `az ad app update` | This flag doesn't exist. Use `--set spa='{"redirectUris":[...]}'` instead. | 2026-02-10 |
| Streamable HTTP curl without Accept header | `/mcp` endpoint returns "Not Acceptable" without `-H "Accept: application/json, text/event-stream"`. | 2026-02-10 |
| Azure AD `accessTokenAcceptedVersion: null` | New App Registrations default to v1 tokens (issuer `sts.windows.net`). `fastapi-azure-auth` expects v2 (issuer `login.microsoftonline.com/.../v2.0`). Fix: `az ad app update --id <id> --set api='{"requestedAccessTokenVersion": 2}'`. Symptom: 401 "Invalid issuer". | 2026-02-11 |
| Bicep full deploy on pre-Bicep envs | Team/demo were created before Bicep IaC. Full Bicep deploy creates new SQL servers, Container App Environments, etc. instead of using existing shared infra. Fix: use `az containerapp update` for image deploys; deploy alerts module standalone. | 2026-02-12 |
| MCP SDK `enable_dns_rebinding_protection=True` with empty `allowed_hosts` | SDK v1.8+ applies host validation at route handler level (not just middleware). Empty allowed_hosts = all requests get 421. Fix: disable in SDK, enforce Origin validation in custom middleware. | 2026-02-12 |
| Docker build without VITE build args | React compiles with `your-tenant-id` placeholder if `--build-arg VITE_*` not passed. Must include `--build-arg VITE_SPA_CLIENT_ID=... VITE_API_CLIENT_ID=... VITE_AZURE_TENANT_ID=... VITE_API_URL=/api` in every ACR build. | 2026-02-12 |
| OAuth resource indicator exact match | Claude sends resource URI with path (e.g., `/mcp`). Exact string match against `OAUTH_BASE_URL` fails. Fix: compare scheme+host only (origin-based matching). | 2026-02-12 |
| Key Vault RBAC propagation on greenfield | Bicep identity module assigns Key Vault Secrets User, then containerapp module creates a revision. If RBAC hasn't propagated (~5-10 min), the K8s secret `capp-<app-name>` is never created. App crash-loops with `secret not found`. Fix: force a new revision after waiting for RBAC propagation. | 2026-02-19 |
| `az containerapp update --image` on first deploy | If the first Bicep deploy fails at containerapp, the K8s secret object for Key Vault refs is never created. `az containerapp update --image` only updates the image — doesn't recreate secret infra. Container crashes, then locks provisioning for ~30 min. Only fix: re-run full Bicep deploy. | 2026-02-19 |
| SPA redirect URI with `/auth/callback` only | MSAL config uses `window.location.origin` (base URL, no path) as redirect URI. Registering only `https://<fqdn>/auth/callback` causes `AADSTS50011` mismatch. Must register both the base URL AND `/auth/callback`. | 2026-02-19 |

---

## Current State

**Phases:**
- Phase 1: SHIPPED (Jan 2026) — Core CRUD, MCP, web UI
- Phase 2: CLOSED (5-12 Feb 2026) — Production hardening, IaC, auth refactor, tenant isolation, OAuth
- Phase 3: IN PROGRESS (12 Feb 2026 –). D workstream (Platform Readiness) complete. A/B/C workstreams pending.

**What's working:**
- 16 MCP tools for meetings (6), actions (7), decisions (3)
- 6 database tables: Meeting, Action, Decision, ClientToken, OAuthClient, RefreshTokenUsage + `_MigrationHistory` tracking table
- 4 transport methods: Streamable HTTP (`/mcp`), SSE (`/sse`), stdio (local), REST (`/api/*`)
- Full CRUD for meetings, actions, decisions via MCP tools. Web UI is read-only for creation (no create/edit forms); only action status updates are supported in UI.
- Delete operations for all entities (cascade delete for meetings done in application code, not FK constraints)
- Azure AD authentication for web UI (with email whitelist)
- MCP authentication (multiple methods):
  - Token auth (query param / Bearer header / X-API-Key) for Claude
  - Path-based token auth for Copilot (`/mcp/{token}`)
  - OAuth 2.1 with DCR + PKCE for ChatGPT (hardened: redirect URI allowlist + token-gated consent + origin-based resource indicator matching + refresh token rotation + token revocation endpoint)
- DB-backed client tokens with SHA256 hashing, 5-min in-memory cache
- Connection pooling (QueuePool) with retry-on-transient decorator (17 Azure SQL error codes)
- Pydantic validation on all 16 MCP tools with field limits
- Tiered rate limiting: MCP 120/min per-token, OAuth 20/min per-IP, API 60/min per-IP. Returns 429 with Retry-After header.
- Attendee and tag filtering on meetings (MCP only; web UI has no attendee filter)
- Transcript storage and search (keyword search with snippet extraction)
- Three environments: team (internal), demo (Mark sign-off), marshall (first client)
- D16 security fixes deployed to team and demo (2026-02-12): 19 fixes across 4 batches, 60 tests passing
- **Security:**
  - Non-root container user (appuser)
  - Security headers on all responses (X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy, Permissions-Policy, Cache-Control on auth endpoints)
  - Origin header validation with DNS rebinding protection
  - CORS restricted to specific methods and headers
  - Tiered rate limiting on auth and API endpoints
  - Pydantic field-level validation with length limits on all MCP tools
  - OAuth client_secret hashed with SHA256
  - Server-side HTML tag stripping on all text inputs
  - Null byte stripping on all text inputs
  - JWT dual-key rotation support (JWT_SECRET_PREVIOUS)
  - OAuth refresh token rotation on use (RFC-compliant)
  - Token revocation endpoint (`/oauth/revoke`, RFC 7009)
  - RFC 9728 protected resource metadata (`/.well-known/oauth-protected-resource`)
  - MCP-Protocol-Version header validation
  - RFC 8707 resource indicators
  - Migration framework with checksum verification and rollback support
- **Observability:**
  - Application Insights telemetry (via azure-monitor-opentelemetry)
  - Structured logging (no print statements)
  - Health probes (Liveness `/health/live` + Readiness `/health/ready`)
  - Azure SQL Auditing (90-day retention)
  - Budget alerts ($35 AUD/month: 80% warning, 100% critical)
  - Azure Monitor alert rules (7 per env): 5xx errors, response time, container restarts, replica-zero (client envs only), CPU, memory, auth failure spike
  - Pre-deploy vulnerability scanning via `infra/audit.sh`
- **Infrastructure as Code:** Bicep templates (6 modules) managing Container App, SQL, Key Vault, monitoring, identity/RBAC
  - Note: team/demo are pre-Bicep environments — use `az containerapp update` for image deploys, deploy Bicep modules (e.g., alerts) standalone. Full Bicep deploy is for new environments only (e.g., marshall).
- **Documentation package** (14 polished docs + 2 drafts in Second Brain `3-delivery/`):
  - system-overview, user-guide, platform-setup, architecture, security
  - deployment-guide, admin-database, user-admin, cost-summary, troubleshooting
  - reference-architecture, client-offering, data-sovereignty-position, backup-restore-runbook
  - Drafts: marshall-handover-draft.md, Reference Architecture .docx
- **Working docs in repo** (`/docs/`, 19 files): ADRs, deployment briefs, implementation specs, audit reports, stress test results, best practice comparison, incident playbook, offboarding runbook, SLA/RPO/RTO

**Known issues:**
- ~~Cold start delay~~ measured at 209ms TTFB (D14) — not an issue
- No email notifications for actions
- ChatGPT requires connector to be manually enabled in Tools menu per chat
- `get_decision()` exists in `tools/decisions.py` but has no MCP wrapper
- `ExpandableText` component exists in web UI but is unused (leftover from earlier approach)
- `meetingsApi.search()` defined in `web/src/services/api.js` but not used in any UI component
- Marshall pending D16 rollout — migration 003 + ChatGPT re-auth required
- CI/CD not automated (manual deploy with pre-deploy audit script)

---

## Technical Debt

- [ ] No integration tests or CI — `test_validation.py` has 60 unit tests for schema validation, but no integration tests, and no CI pipeline to run them
- [ ] Hardcoded `system@generationai.co.nz` for MCP user attribution (`mcp_server.py:34`)
- [ ] Log Analytics workspaces created per environment (could consolidate)
- [ ] Legacy `meeting-intelligence-v2-rg` resource group still exists (can delete)
- [ ] OAuth 2.1 auth codes stored in-memory — lost on container restart (clients persist to DB via OAuthClient table, but pending auth codes do not)

---

## Dependencies

| Package | Version | Why |
|---------|---------|-----|
| FastAPI | latest | Web framework with async support |
| mcp[cli] | >=1.8.0,<2.0.0 | Model Context Protocol SDK (Streamable HTTP) |
| pyodbc | latest | Azure SQL connectivity |
| pydantic-settings | latest | Environment config management |
| PyJWT | latest | OAuth 2.1 JWT token handling |
| React | 18.x | Frontend framework |
| MSAL React | latest | Azure AD authentication |
| Vite | latest | Frontend build tool |

---

## Agent Instructions

When working in this codebase:

1. **Read this file first** before making changes
2. **Don't review code unless asked** — context window is expensive
3. **Follow existing patterns** — check the Patterns section above
4. **Update this file** when you make significant changes
5. **Deploy changes** using `./infra/deploy-bicep.sh [env]` - use unique image tags

**Before writing code:**
- Confirm you understand the architecture
- Check "What's Been Tried & Failed" to avoid repeating mistakes
- For non-trivial changes, outline approach before implementing

**Deployment notes:**
- Always use a unique image tag: `./infra/deploy-bicep.sh marshall $(date +%Y%m%d%H%M%S)`
- `deploy.sh` is deprecated — use `infra/deploy-bicep.sh` for new environments (marshall)
- **Pre-Bicep environments (team/demo):** Use `az containerapp update --image` for image deploys. Deploy Bicep modules (e.g., alerts) standalone. Full Bicep deploy creates new per-env infra — do NOT use.
- **ACR builds must include VITE build args:** `--build-arg VITE_SPA_CLIENT_ID=b5a8a565-e18e-42a6-a57b-ade6d17aa197 --build-arg VITE_API_CLIENT_ID=b5a8a565-e18e-42a6-a57b-ade6d17aa197 --build-arg VITE_AZURE_TENANT_ID=12e7fcaa-f776-4545-aacf-e89be7737cf3 --build-arg VITE_API_URL=/api`
- After deploy, reconnect MCP in Claude to refresh tool list
- Check revision status: `az containerapp revision list --name [app] --resource-group [rg] -o table`

---

## Second Brain Sync

This repo is linked to a project folder in Second Brain. See `.claude/REPO-SYNC-INSTRUCTIONS.md` for the full sync process.

### Absolute Paths

| Location | Absolute Path |
|----------|---------------|
| Project folder | `/Users/caleblucas/Second Brain/Project Management/Projects/GenerationAI - Meeting Intelligence System/` |
| Skills folder | `/Users/caleblucas/Second Brain/Project Management/Skills/` |
| CHANGELOG | `/Users/caleblucas/Second Brain/Project Management/CHANGELOG.md` |

### Primary Sync Target

**`_repo-context.md`** — Mandatory. Update at session end with architecture, recent changes, tech debt, and current state. This is the standard interface between repo-side and Cowork-side agents.

### Additional Sync Files (Project-Specific)

These supplement `_repo-context.md` for this project:

| When | Update | Full Path |
|------|--------|-----------|
| Session end | `_repo-context.md` | `.../GenerationAI - Meeting Intelligence System/_repo-context.md` |
| Session end | `_repo-link.md` sync date | `.../GenerationAI - Meeting Intelligence System/_repo-link.md` |
| Status/milestone change | `_status.md` | `.../GenerationAI - Meeting Intelligence System/_status.md` |
| Key decision made | `mi-decisions.md` | `.../GenerationAI - Meeting Intelligence System/2-build/mi-decisions.md` |
| Sprint work done | `mi-sprint-execution.md` | `.../GenerationAI - Meeting Intelligence System/2-build/mi-sprint-execution.md` |
| Learned reusable pattern | Skill file | `/Users/caleblucas/Second Brain/Project Management/Skills/[skill-name]/SKILL.md` |
| Session ends | CHANGELOG | `/Users/caleblucas/Second Brain/Project Management/CHANGELOG.md` |

### Files That Must Stay In Sync

When project status changes, update ALL of these together:
1. **This file** (`CLAUDE.md`) — Project Status field and Current State section
2. **`_repo-context.md`** — Current State and Recent Changes
3. **`_status.md`** — Stage field and Current State section

### How to Update

1. Navigate to the absolute path listed above
2. Update the file directly
3. Verify the change was saved

If you don't have access to Second Brain folder:
1. Note the update needed at the end of your response
2. Format: `📝 Second Brain update needed: [what to update]`

**MANDATORY:** Never leave these files out of sync. If CLAUDE.md says "BUILD" but _status.md says "SHIP", that's a bug.

---

## Environments

| Environment | Web URL | Database | Scale | Purpose |
|-------------|---------|----------|-------|---------|
| Team | meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io | meeting-intelligence-team | 0-10 | Internal use |
| Demo | meeting-intelligence.ambitiousbay-58ea1c1f.australiaeast.azurecontainerapps.io | meeting-intelligence | 0-10 | Mark sign-off |
| Marshall | mi-marshall.delightfulpebble-aa90cd5c.australiaeast.azurecontainerapps.io | mi-marshall | 1-10 | First client (John Marshall) |
| Testing Instance | mi-testing-instance.icycliff-e324f345.australiaeast.azurecontainerapps.io | mi-testing-instance | 1-10 | Client demos (Mark) |

**Estimated monthly cost:** ~$33 AUD (team + demo scale-to-zero), Marshall + testing-instance are always-on (minReplicas=1)

---

## MCP Tools Available

| Category | Tools |
|----------|-------|
| Meetings | list_meetings, get_meeting, search_meetings, create_meeting, update_meeting, delete_meeting |
| Actions | list_actions, get_action, create_action, update_action, complete_action, park_action, delete_action |
| Decisions | list_decisions, create_decision, delete_decision |

---

## Skills Used

| Skill | Absolute Path | Last Synced |
|-------|---------------|-------------|
| azure-container-apps | `/Users/caleblucas/Second Brain/Project Management/Skills/azure-container-apps/SKILL.md` | 2026-02-05 |
| mcp-copilot-integration | `/Users/caleblucas/Second Brain/Project Management/Skills/mcp-copilot-integration/SKILL.md` | 2026-02-04 |
| mcp-chatgpt-integration | `/Users/caleblucas/Second Brain/Project Management/Skills/mcp-chatgpt-integration/SKILL.md` | 2026-02-05 |

---

## Links

- **Project folder:** `Second Brain/Project Management/Projects/GenerationAI - Meeting Intelligence System/`
- **Decision log:** `Second Brain/Project Management/Projects/GenerationAI - Meeting Intelligence System/2-build/mi-decisions.md`
- **Azure Resource Groups:** meeting-intelligence-dev-rg, meeting-intelligence-team-rg, meeting-intelligence-prod-rg
- **SQL Server:** genai-sql-server (in rg-generationAI-Internal)
- **Container Registry:** meetingintelacr20260116 (in meeting-intelligence-v2-rg)

---

## Session End Checklist

**BEFORE ending any session, CHECK and UPDATE these files:**

### Mandatory Updates

1. **CHANGELOG** (`/Users/caleblucas/Second Brain/Project Management/CHANGELOG.md`)
   - Add session entry if significant work was done
   - Use format: `## [Date] (Session N — [Topic])`

2. **Status sync** — If project status changed:
   - `CLAUDE.md` (this file)
   - `_status.md` in Second Brain
   - `mi-sprint-execution.md` if sprint-related

### Skill Updates (if applicable)

Check these triggers:
- "This worked better than expected" → Update relevant skill
- "I wouldn't do it that way again" → Add to skill's gotchas
- "This pattern would work for other projects" → Create new skill

Where to update:
- Skills live at `/Users/caleblucas/Second Brain/Project Management/Skills/[skill-name]/SKILL.md`
- New skills use template at `Templates/skill-template.md`

### This File Updates (if applicable)

- Learned something that failed? → Add to "What's Been Tried & Failed"
- Added technical debt? → Add to Technical Debt section
- Changed architecture or features? → Update relevant sections

---

*This file is the technical context for agents. Keep it current.*

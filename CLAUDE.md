# Meeting Intelligence System - Agent Context

**Last Updated:** 2026-02-05
**Project Status:** BUILD
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
./deploy.sh prod  # or dev/team
```

**Required environment variables (in `.env.deploy`):**
- `AZURE_SQL_SERVER` — Azure SQL server hostname
- `AZURE_SQL_DATABASE` — Database name
- `MCP_AUTH_TOKENS` — JSON map of token hashes to emails
- `ALLOWED_USERS` — Comma-separated emails for web UI access
- `CORS_ORIGINS` — Allowed CORS origins
- `JWT_SECRET` — Secret for OAuth JWT tokens
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
| `deploy.sh` | Deployment script for all environments |
| `.env.deploy` | Secrets (not in git) |
| `schema.sql` | Database schema definition |

---

## Patterns & Conventions

- **Error responses**: All DB operations return `{"error": True, "code": "...", "message": "..."}` on failure
- **Dates**: ISO 8601 format everywhere
- **Status values**: "Open", "Complete", "Parked" (exact strings)
- **Tags**: Comma-separated lowercase strings (e.g., "planning, engineering")
- **Attendees**: Comma-separated email addresses
- **Auth tokens**: Hash IS the token - users send the SHA256 hash, not plaintext
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

---

## Current State

**What's working:**
- Full CRUD for meetings, actions, decisions via MCP and web UI
- Delete operations for all entities (including cascade delete for meetings)
- Azure AD authentication for web UI
- MCP authentication (multiple methods):
  - Token auth (query param / Bearer header) for Claude
  - Path-based token auth for Copilot (`/mcp/{token}`)
  - OAuth 2.1 with PKCE for ChatGPT (team instance only)
- Streamable HTTP transport (`/mcp`) for Copilot and ChatGPT
- SSE transport (`/sse`) for Claude Desktop
- Attendee and tag filtering on meetings
- Transcript storage and search
- Two environments: team (internal), demo (Mark sign-off)
- **Observability (team instance):**
  - Application Insights telemetry
  - Structured logging (no print statements)
  - Health probes (Liveness + Readiness)
  - Azure SQL Auditing (90-day retention)
- **Documentation package complete** (10 docs in `/docs`):
  - system-overview.md, user-guide.md, platform-setup.md
  - architecture.md, security.md, deployment-guide.md
  - admin-database.md, user-admin.md, cost-summary.md, troubleshooting.md

**What's in progress (Phase 2 Days 6-10):**
- ChatGPT MCP testing (OAuth implemented on team instance, needs end-to-end testing)
- Mark sign-off

**Known issues:**
- Cold start delay (2-5 sec) when apps scale from 0
- No email notifications for actions
- No Fireflies integration (removed)
- ChatGPT requires connector to be manually enabled in Tools menu per chat

---

## Technical Debt

- [ ] No test suite - this is MVP, tests not written
- [ ] Hardcoded `system@generationai.co.nz` for MCP user attribution
- [ ] Log Analytics workspaces created per environment (could consolidate)
- [ ] Legacy `meeting-intelligence-v2-rg` resource group still exists (can delete)
- [ ] MCP auth tokens use old @myadvisor.co.nz domain in mapping
- [ ] OAuth 2.1 uses in-memory storage - clients/codes lost on container restart (fine for MVP)

---

## Dependencies

| Package | Version | Why |
|---------|---------|-----|
| FastAPI | latest | Web framework with async support |
| mcp[cli] | >=1.8.0 | Model Context Protocol SDK (Streamable HTTP) |
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
5. **Deploy changes** using `./deploy.sh [env]` - use unique image tags

**Before writing code:**
- Confirm you understand the architecture
- Check "What's Been Tried & Failed" to avoid repeating mistakes
- For non-trivial changes, outline approach before implementing

**Deployment notes:**
- Always use a unique image tag: `IMAGE_TAG="$(date +%Y%m%d%H%M%S)" ./deploy.sh prod`
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

**Estimated monthly cost:** ~$33 AUD (both scale-to-zero)

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

# Meeting Intelligence System - Agent Context

**Last Updated:** 2026-02-04
**Project Status:** SHIP
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
- `SQL_SERVER` — Azure SQL server hostname
- `AZURE_CLIENT_ID` — Managed Identity client ID for DB auth
- `MCP_AUTH_TOKENS` — JSON map of token hashes to emails
- `ALLOWED_USERS` — Comma-separated emails for web UI access
- `CORS_ORIGINS` — Allowed CORS origins
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

---

## Current State

**What's working:**
- Full CRUD for meetings, actions, decisions via MCP and web UI
- Delete operations for all entities (including cascade delete for meetings)
- Azure AD authentication for web UI
- Token auth for MCP/Claude
- Attendee and tag filtering on meetings
- Transcript storage and search
- Three environments: dev, team, prod

**What's in progress:**
- Nothing currently

**Known issues:**
- Cold start delay (2-5 sec) when apps scale from 0
- No email notifications for actions
- No Fireflies integration (removed)

---

## Technical Debt

- [ ] No test suite - this is MVP, tests not written
- [ ] Hardcoded `system@generationai.co.nz` for MCP user attribution
- [ ] Log Analytics workspaces created per environment (could consolidate)
- [ ] Legacy `meeting-intelligence-v2-rg` resource group still exists (can delete)
- [ ] MCP auth tokens use old @myadvisor.co.nz domain in mapping

---

## Dependencies

| Package | Version | Why |
|---------|---------|-----|
| FastAPI | latest | Web framework with async support |
| mcp | latest | Model Context Protocol SDK |
| pyodbc | latest | Azure SQL connectivity |
| pydantic-settings | latest | Environment config management |
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

This repo is linked to a project folder in Second Brain. **Keep them in sync.**

**Second Brain path:** `Second Brain/Project Management/Projects/GenerationAI - Meeting Intelligence System/`

### What to Update in Second Brain

| When | Update |
|------|--------|
| Repo created / moved | `_repo-link.md` in project folder |
| Major milestone reached | `_status.md` — Current State section |
| Key decision made | `2-build/mi-decisions.md` |
| Learned reusable pattern | `Skills/[skill-name]/SKILL.md` |
| Session ends | `CHANGELOG.md` (if significant work done) |

### How to Update

If you have access to Second Brain folder:
1. Navigate to the project folder path above
2. Update the relevant file directly

If you don't have access:
1. Note the update needed at the end of your response
2. Format: `📝 Second Brain update needed: [what to update]`

**Don't let the two get out of sync.** If CLAUDE.md says "in progress" but _status.md says "shipped", someone will get confused.

---

## Environments

| Environment | Web URL | Database | Scale |
|-------------|---------|----------|-------|
| Dev | meeting-intelligence-dev.victoriousbush-9db31fb8.australiaeast.azurecontainerapps.io | meeting-intelligence-dev | 0-1 |
| Team | meeting-intelligence-team.happystone-42529ebe.australiaeast.azurecontainerapps.io | meeting-intelligence-team | 0-10 |
| Prod | meeting-intelligence.ambitiousbay-58ea1c1f.australiaeast.azurecontainerapps.io | meeting-intelligence | 0-10 |

**Estimated monthly cost:** ~$28 AUD (all scale-to-zero)

---

## MCP Tools Available

| Category | Tools |
|----------|-------|
| Meetings | list_meetings, get_meeting, search_meetings, create_meeting, update_meeting, delete_meeting |
| Actions | list_actions, get_action, create_action, update_action, complete_action, park_action, delete_action |
| Decisions | list_decisions, create_decision, delete_decision |

---

## Skills Used

| Skill | Path | Last Synced |
|-------|------|-------------|
| azure-container-apps | `Second Brain/Project Management/Skills/azure-container-apps/SKILL.md` | 2026-02-04 |

---

## Links

- **Project folder:** `Second Brain/Project Management/Projects/GenerationAI - Meeting Intelligence System/`
- **Decision log:** `Second Brain/Project Management/Projects/GenerationAI - Meeting Intelligence System/2-build/mi-decisions.md`
- **Azure Resource Groups:** meeting-intelligence-dev-rg, meeting-intelligence-team-rg, meeting-intelligence-prod-rg
- **SQL Server:** genai-sql-server (in rg-generationAI-Internal)
- **Container Registry:** meetingintelacr20260116 (in meeting-intelligence-v2-rg)

---

## Session End — Skill Sync

Before ending any session, ask:

1. **Did I learn a reusable pattern?** → Update the relevant skill in Second Brain
2. **Did I find a better way to do something the skill describes?** → Update the skill
3. **Did I discover API/tool behaviour that differs from docs?** → Add to skill
4. **Is there a new pattern worth capturing?** → Create new skill using `Templates/skill-template.md`
5. **Did I find something that differs from expectations?** → Add to "What's Been Tried & Failed"
6. **Did I add technical debt?** → Add to Technical Debt section
7. **Did I change the architecture or add features?** → Update this file

**Update the skill in Second Brain, not here.** This file references skills; it doesn't duplicate them.

**Triggers that should prompt skill updates:**
- "This worked better than expected"
- "I wouldn't do it that way again"
- "This pattern would work for other projects"

---

*This file is the technical context for agents. Keep it current.*

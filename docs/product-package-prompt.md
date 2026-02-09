# Product Package Documentation - Implementation Prompt

**Task:** Complete the product package documentation for Meeting Intelligence.

**Context:** An audit against the product-package skill identified missing documentation. The system is functionally complete (BUILD phase done) and needs productisation docs for Day 7-9.

---

## Current State

### Exists (Don't Recreate)
| Document | Location | Status |
|----------|----------|--------|
| Platform Setup | `docs/platform-setup.md` | ✅ Complete |
| Security Posture | `docs/security.md` | ✅ Complete |
| Admin Guide (Database) | `docs/admin-database.md` | ✅ Complete |
| Admin Guide (Users) | `docs/user-admin.md` | ✅ Complete |

### Missing (Create These)
| Document | Priority | Target Location |
|----------|----------|-----------------|
| System Overview | Must Have | `docs/system-overview.md` |
| User Guide | Must Have | `docs/user-guide.md` |
| Architecture Doc | Should Have | `docs/architecture.md` |
| Deployment Guide | Should Have | `docs/deployment-guide.md` |
| Cost Summary | Should Have | `docs/cost-summary.md` |
| Troubleshooting | Nice to Have | `docs/troubleshooting.md` |

---

## Source Information

Read these files to gather content:

1. **CLAUDE.md** - System architecture, commands, MCP tools, environments
2. **deploy.sh** - Deployment process, environment config
3. **server/src/main.py** - Entry point, modes (--http, stdio)
4. **server/src/mcp_server.py** - MCP tool definitions
5. **web/src/App.jsx** - React app structure
6. **schema.sql** - Database schema
7. **docs/security.md** - Security details (reference, don't duplicate)
8. **docs/platform-setup.md** - Platform connections (reference, don't duplicate)

For cost information, check Azure pricing:
- Azure Container Apps: Scale to zero, ~$0 idle, ~$0.000012/vCPU-second active
- Azure SQL Basic: ~$7/month
- Azure Container Registry Basic: ~$5/month

---

## Document Templates

### 1. System Overview (`docs/system-overview.md`)

```markdown
# Meeting Intelligence

## What It Does
[2-3 sentences: meeting data management system with MCP integration for AI assistants, web UI for humans, tracks meetings/actions/decisions]

## Key Features
- Store and search meeting transcripts and summaries
- Track action items with owners and due dates
- Record decisions with context
- Access via Claude (MCP), web browser, or direct database
- Multi-platform AI support (Claude Desktop, Claude Code, M365 Copilot, ChatGPT)

## Who It's For
[Teams who want AI assistants to help manage meeting follow-ups]

## How to Access
- Web UI: [URLs for dev/team/prod]
- Claude Desktop: See platform-setup.md
- M365 Copilot: See platform-setup.md
- API: REST endpoints at /api/*

## Current Status
[Production - 3 environments: dev, team, prod]
```

### 2. User Guide (`docs/user-guide.md`)

```markdown
# User Guide

## Getting Started

### First-Time Setup
1. Get added to ALLOWED_USERS by an admin
2. Visit the web URL
3. Sign in with Microsoft account
4. (Optional) Set up Claude Desktop with MCP token

### Web Interface
[Screenshot placeholder - describe the main views]

## Common Tasks

### View Recent Meetings
[Steps for web UI and Claude]

### Create a Meeting Record
[Steps - manual entry vs Fireflies sync]

### Track Action Items
[Steps - create, assign, complete, search by owner]

### Record Decisions
[Steps - link to meeting, add context]

### Search Meetings
[Steps - keyword search, filter by date/attendee/tag]

## Using with Claude

### Available Commands
[List the MCP tools in natural language]

### Example Prompts
- "Show me my open action items"
- "What decisions did we make in last week's planning meeting?"
- "Create an action for @mark to review the proposal by Friday"
- "Search meetings for 'budget'"

## Tips
- Use tags to categorise meetings (e.g., "standup", "planning", "client")
- Attendees should be email addresses for filtering
- Action owners should match how people search (email or name)
```

### 3. Architecture Doc (`docs/architecture.md`)

```markdown
# Architecture

## High-Level Diagram
[Copy from CLAUDE.md, expand with more detail]

## Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| API Server | Python/FastAPI | REST API + MCP server |
| Web Frontend | React/Vite | Browser interface |
| Database | Azure SQL | Data persistence |
| Container Host | Azure Container Apps | Application hosting |
| Registry | Azure Container Registry | Docker images |

## Data Flow

### Web UI Flow
[User → React → FastAPI → Azure SQL]

### MCP Flow
[Claude → SSE/HTTP → FastAPI → Azure SQL]

## Infrastructure

| Resource | Service | Region | Monthly Cost |
|----------|---------|--------|--------------|
| App (dev) | Container Apps | Australia East | ~$7 |
| App (team) | Container Apps | Australia East | ~$7 |
| App (prod) | Container Apps | Australia East | ~$7 |
| Database (3x) | Azure SQL Basic | Australia East | ~$21 |
| Registry | ACR Basic | Australia East | ~$5 |

## Security Model
[Reference docs/security.md]

## Key Decisions
- Single Dockerfile for frontend+backend (simplicity)
- Azure Managed Identity for database (no passwords)
- Scale-to-zero for cost optimisation
- SSE + Streamable HTTP for MCP (platform compatibility)
```

### 4. Deployment Guide (`docs/deployment-guide.md`)

```markdown
# Deployment Guide

## Prerequisites
- Azure CLI installed and logged in
- Access to the Azure subscription
- Git repository cloned locally
- `.env.deploy` file with secrets

## Environment Setup

### Required Secrets (.env.deploy)
```
MCP_AUTH_TOKENS={"hash1":"email1","hash2":"email2"}
ALLOWED_USERS=email1,email2
CORS_ORIGINS=https://url1,https://url2
```

### Environments
| Environment | Resource Group | Database |
|-------------|----------------|----------|
| dev | meeting-intelligence-dev-rg | meeting-intelligence-dev |
| team | meeting-intelligence-team-rg | meeting-intelligence-team |
| prod | meeting-intelligence-prod-rg | meeting-intelligence |

## Deployment Steps

### Standard Deployment
```bash
./deploy.sh dev    # or team/prod
```

### What deploy.sh Does
1. Creates resource group if needed
2. Creates ACR if needed
3. Builds Docker image with frontend baked in
4. Pushes to Azure Container Registry
5. Creates/updates Container App with env vars
6. Outputs the URL

### Force New Image Tag
```bash
IMAGE_TAG="$(date +%Y%m%d%H%M%S)" ./deploy.sh dev
```

## Updating

### Code Changes
1. Commit changes to git
2. Run `./deploy.sh <env>`
3. Verify at the URL

### Environment Variable Changes
1. Update `.env.deploy`
2. Run `./deploy.sh <env>` (redeploy required)

## Rollback

### Quick Rollback
```bash
# Find previous image tag
az acr repository show-tags -n meetingintelacr20260116 --repository meeting-intelligence-dev

# Deploy specific tag
IMAGE_TAG="previous-tag" ./deploy.sh dev
```

### Database Rollback
Use Azure SQL point-in-time restore (Azure Portal → SQL Database → Restore).

## Infrastructure as Code
- `deploy.sh` - Main deployment script
- `server/Dockerfile` - Container definition
- `schema.sql` - Database schema

## Health Checks
The app exposes `/health` endpoint. Container Apps probes:
- Liveness: `/health` every 10s
- Readiness: `/health` every 5s
```

### 5. Cost Summary (`docs/cost-summary.md`)

```markdown
# Cost Summary

## Current Monthly Cost

| Resource | Service | Cost/Month | Notes |
|----------|---------|------------|-------|
| Container Apps (x3) | Azure Container Apps | ~$21 | Scale-to-zero, ~$7 each |
| Databases (x3) | Azure SQL Basic | ~$21 | 5 DTU, ~$7 each |
| Container Registry | ACR Basic | ~$5 | Shared across envs |
| **Total** | | **~$47/month** | |

*Actual costs depend on usage. Scale-to-zero means near-zero when idle.*

## Cost Drivers

1. **Database** - Fixed cost regardless of usage (Basic tier)
2. **Compute** - Pay per second when handling requests
3. **Storage** - Minimal (ACR images, SQL storage)

## Optimisations Applied

- **Scale-to-zero**: Container Apps scale down when idle
- **Basic SQL tier**: 5 DTU sufficient for small teams
- **Shared ACR**: Single registry for all environments
- **No Application Gateway**: Direct Container Apps ingress
- **Managed Identity**: No Key Vault needed for DB credentials

## Scaling Costs

| Scale | Users | Requests/day | Est. Cost |
|-------|-------|--------------|-----------|
| Current | 5 | 100 | ~$47/mo |
| 10x | 50 | 1,000 | ~$55/mo |
| 100x | 500 | 10,000 | ~$80/mo |

SQL becomes the bottleneck at scale. Upgrade path: Basic → Standard → Premium.

## Cost Monitoring

Azure Portal → Cost Management → Cost analysis → Filter by resource group.
```

### 6. Troubleshooting (`docs/troubleshooting.md`)

```markdown
# Troubleshooting

## Common Issues

### Can't Sign In (Web UI)

**Symptom:** 403 Forbidden after Microsoft login

**Cause:** Email not in ALLOWED_USERS

**Fix:**
1. Check email is in ALLOWED_USERS env var (exact match)
2. Redeploy if you added it
3. Try incognito window (cached token)

---

### MCP Connection Failed

**Symptom:** Claude can't connect to MCP server

**Cause:** Token invalid or server unreachable

**Fix:**
1. Verify token (not the hash) in Claude Desktop config
2. Check URL format matches platform-setup.md
3. Test URL in browser (should return "MCP server running")
4. Check container is running in Azure Portal

---

### Tools Not Showing in ChatGPT

**Symptom:** OAuth works but no tools visible

**Cause:** Developer Mode not enabled

**Fix:** Enable Developer Mode in ChatGPT settings (see platform-setup.md)

---

### Container Won't Start

**Symptom:** Deployment succeeds but app returns 503

**Cause:** Missing environment variables or crash on startup

**Fix:**
1. Check Azure Portal → Container Apps → Logs
2. Verify all required env vars set
3. Check for Python exceptions in logs

---

### Database Connection Failed

**Symptom:** 500 errors, "connection refused" in logs

**Cause:** Managed Identity not configured or firewall issue

**Fix:**
1. Check Container App has system-assigned identity
2. Check identity is added as database user
3. Check Azure SQL firewall allows Azure services

---

### Slow Response Times

**Symptom:** First request takes 10+ seconds

**Cause:** Cold start (scale-to-zero)

**Fix:** This is expected. First request wakes the container. Set min-replicas=1 if unacceptable (increases cost).

---

## Getting Help

1. Check container logs: Azure Portal → Container Apps → Logs
2. Check database: Azure Portal → SQL Database → Query editor
3. Check this documentation
4. Contact: [admin contact]

## Log Locations

| Log Type | Location |
|----------|----------|
| Application logs | Azure Portal → Container Apps → Logs |
| Auth failures | Azure AD sign-in logs |
| Database queries | Azure SQL → Query Performance Insight |
| Deployment logs | Azure Portal → Container Apps → Revisions |
```

---

## Instructions

1. **Read source files** listed above to gather accurate information
2. **Create each document** in order of priority (System Overview first)
3. **Follow templates** but adapt content to match actual system state
4. **Cross-reference** existing docs to avoid duplication
5. **Use NZ spelling** (organisation, optimisation, etc.)
6. **Keep it concise** — these are working docs, not marketing

## Validation

After creating all docs, verify:
- [ ] All 6 new docs exist in `/docs`
- [ ] Links between docs work
- [ ] No contradictions with existing docs
- [ ] Dates are "February 2026"
- [ ] URLs match actual deployments

## Output

Update `_status.md` to mark Day 7-9 (productisation docs) complete when done.

# Meeting Intelligence — Backlog

Items noted but not yet actioned. Organised by category. Reference this file in agent briefs when picking up work.

**Last updated:** 23 February 2026

---

## Web UI Enhancements

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| W1 | Column sorting on tables (click column header to sort by owner, date, status, etc.) | Medium | Applies to meetings, actions, decisions tables |
| W2 | Fix "all" actions filter — only shows open actions regardless of selection | Medium | Bug #1 in `_bugs.md` |
| W3 | Owner field dropdown — can't freely type new owner names | Medium | Bug #5 in `_bugs.md` |
| W4 | Meeting time shows 12:00 AM in detail header — needs actual time from transcript | Medium | Bug #4 in `_bugs.md`, part code / part prompting |
| W5 | Remove unused `ExpandableText` component | Low | Leftover from earlier approach |
| W6 | Wire up `meetingsApi.search()` — defined in `api.js` but not used in any UI component | Low | Could enable search bar in web UI |
| W7 | Attendee filtering in web UI (exists in MCP only) | Low | |

## Application / Server

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| A1 | Wire up `get_decision()` MCP wrapper — function exists in `tools/decisions.py` but no MCP tool registered | Medium | |
| A2 | OAuth auth codes stored in-memory — lost on container restart | Medium | Technical debt. OAuthClient persists to DB but pending auth codes do not |
| A3 | Hardcoded `system@generationai.co.nz` for MCP user attribution | Low | `mcp_server.py:34` |
| A4 | Email notifications for actions | Low | No current implementation |
| A5 | Two-database model (team + personal per client) | Low | Design decision from architecture doc. Needs schema, routing, Key Vault changes |
| A6 | Transcript storage decision — `RawTranscript` column exists but usage/policy not confirmed | Low | Architecture doc says transcripts not stored; schema supports it. Decide and align |

## Infrastructure / DevOps

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| I1 | CI/CD pipeline (GitHub Actions) | High | No automated testing or deployment. Manual deploy with pre-deploy audit script |
| I2 | Deploy pipeline automation — AcrPull, CORS, SQL setup, migrations, token gen, redirect URIs | High | ~1 week scripting. See `deploy-log-testing-instance.md` for full gap list |
| I3 | Marshall D16 rollout — migration 003 + image deploy + ChatGPT re-auth | High | Pending since 12 Feb |
| I4 | IaC template scanning (Checkov) | Low | Add when CI/CD pipeline exists |
| I5 | Consolidate Log Analytics workspaces | Low | Currently one per environment |
| I6 | Delete legacy `meeting-intelligence-v2-rg` resource group | Low | |
| I7 | NZ North migration (from AU East) | Low | Confirmed available. Move when deploying under Craig's model |

## Security Hardening (LATER)

Items flagged in D15/D16 as not worth fixing now. Revisit at scale or per-client.

| # | Description | Trigger |
|---|-------------|---------|
| S1 | Private endpoints for Azure SQL (~$8/mo per endpoint) | Enterprise client requirement |
| S2 | VNet integration for Container Apps | Enterprise client requirement |
| S3 | Microsoft Defender for Containers ($7/mo per cluster) | 10+ clients |
| S4 | Signed container images | Nice-to-have, no immediate risk |
| S5 | Conditional access policies (Entra ID) | Per-client assessment |
| S6 | Sequential IDs to UUIDs | Breaking schema change, low actual risk with tenant isolation |
| S7 | PII scrubbing in telemetry | After data retention policy finalised |
| S8 | Consolidated SQL Servers (one server, multiple DBs) | 10+ clients, architectural change |
| S9 | FortiVM shared firewall (geo-blocking, DDoS, packet inspection) | Client volume warrants it. Craig's recommendation |

## Prompting / AI Tool Quality

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| P1 | Email addresses stored as owner instead of display names | Medium | Bug #6 |
| P2 | Due dates not recorded when AI tools create actions | Medium | Bug #7 |
| P3 | Summary field not sent in markdown format — loses structure | Medium | Bug #8 |

---

## Bugs

Full bug list maintained in `2-build/_bugs.md` (Second Brain). Items above are cross-referenced where applicable.

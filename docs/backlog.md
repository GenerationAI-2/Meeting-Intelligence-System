# Meeting Intelligence — Backlog

Single source of truth for all known issues, tech debt, and future work. Do not duplicate items elsewhere — reference this file.

**Last updated:** 27 February 2026

---

## Prehandover (Beta Client Critical)

Must complete before handing a client their login.

### Code — MERGED to main

| # | Description | Status | Notes |
|---|-------------|--------|-------|
| A10 | Self-service PAT generation (Settings page, generate/list/revoke) | DONE | Merged `f204201`. Three provisioning states. |
| W10 | Hide admin UI from non-org-admin users | DONE | Merged `f204201`. Frontend gate + redirect guard. |
| W8 | Workspace switch re-fetches page data | DONE | Merged `f204201`. workspaceVersion counter. |
| W5 | Remove unused ExpandableText component | DONE | Merged `f204201`. Deleted. |
| W6 | Wire up meetingsApi.search() | DONE | Was already implemented — no changes needed. |

### Docs — NOT STARTED

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| DOC1 | Quick Start Guide — connect tools, workflow + prompt examples, Fireflies setup, self-service tokens, skill reference | NOW | Single client-facing doc. Replaces P9, P10, P14. |
| DOC2 | Technical Architecture Brief — for Craig's team, 3-4 pages | NOW | Replaces D1, D3. |
| DOC3 | Client Deploy Runbook — end-to-end deploy checklist | DONE | `docs/DOC3-client-deploy-runbook.md`. Needs Caleb review. |
| DOC4 | Break-glass / Ops Runbook — rollback, PITR, token revocation, escalation | DONE | `docs/DOC4-breakglass-ops-runbook.md`. Needs Caleb review + escalation contacts. |

### Verification — NOT STARTED

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| V1 | B2 live token refresh verification | NOW | ~1hr real usage |
| I11 | Redeploy testing-instance + marshall with current image | PARTIAL | Testing-instance redeployed (27 Feb, 5 deploys). Control DB set up. Marshall still frozen on `f3758d1`. |

---

## Web UI Enhancements

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| W1 | Column sorting on tables (click column header) | Medium | Applies to meetings, actions, decisions tables |
| W2 | ~~Fix "all" actions filter~~ | DONE | Default changed to All. Committed `52bd364`. |
| W3 | Owner field dropdown — can't freely type new owner names | Medium | |
| W4 | Meeting time shows 12:00 AM — needs actual time from transcript | Medium | Part code / part prompting |
| W7 | Attendee filtering in web UI (exists in MCP only) | Low | |

## Application / Server

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| A1 | Wire up `get_decision()` MCP wrapper — function exists but no MCP tool | Medium | |
| A2 | ~~OAuth auth codes stored in-memory~~ | N/A | OAuth 2.1 removed (27 Feb migration). |
| A3 | Hardcoded `system@generationai.co.nz` for MCP user attribution | Low | `mcp_server.py:34` |
| A4 | Email notifications for actions | Low | No current implementation |
| A5 | Two-database model (team + personal per client) | Low | Design decision from architecture doc |
| A6 | Transcript storage decision — `RawTranscript` column exists but usage not confirmed | Low | Architecture doc says not stored; schema supports it |
| A7 | Remove legacy `validate_client_token` fallback | Low | Partially addressed (27 Feb): OAuth removed, SSE removed. Legacy fallback still exists for envs without control DB. |
| A8 | ~~ChatGPT MCP support~~ | N/A | OAuth 2.1 removed (27 Feb migration). ChatGPT would need token-based auth or future re-implementation. |
| A9 | Auto-refresh / polling for web UI — content goes stale | Low | Periodic polling or optimistic refresh on tab focus |

## Infrastructure / DevOps

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| I1 | CI/CD pipeline (GitHub Actions) | High | No automated testing or deployment |
| I2 | Deploy pipeline automation — remaining manual steps | High | ~1 week scripting |
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
| S9 | FortiVM shared firewall (geo-blocking, DDoS, packet inspection) | Client volume warrants it |

## Prompting / AI Tool Quality

| # | Description | Priority | Notes |
|---|-------------|----------|-------|
| P1 | Email addresses stored as owner instead of display names | Medium | |
| P2 | Due dates not recorded when AI tools create actions | Medium | |
| P3 | Summary field not sent in markdown format — loses structure | Medium | |

---

## Completed (reference only)

- **B1-B10** — All 10 bugs fixed (Wave 1 + Wave 2)
- **P1-P8** — Search, schema, column sorting, get_decision, retrieval skill
- **P7** — Workspace architecture. Merged, battle-tested, 229 tests.
- **D14-D16** — Stress test, best practice comparison, research-backed fixes
- **F1-F6** — Deploy pipeline fixes
- **A10, W5, W6, W8, W10** — Prehandover web UI sprint. Merged `f204201`.
- **Profile dropdown + dynamic URLs** — `a4d2f0e`. Settings/Admin under user menu.

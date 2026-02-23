# D13: Build Rationale Audit — Agent Brief

**Project:** Meeting Intelligence System — Phase 3
**Task:** Build Rationale Audit
**Owner:** Repo Agent
**Date:** 12 February 2026

---

## Objective

Audit every major architectural and technology decision in the codebase. For each, document: why it was chosen, what alternatives exist, what the trade-offs are, whether it was a researched decision or an agent default, and whether it's the right choice at 50 clients.

**Output format:** One markdown file per question group (zero rationale, partial rationale, operational). Each entry follows this structure:

```
## [Decision]

**Current implementation:** What's in the code today.
**Why this was chosen:** Best understanding of original reasoning. If unknown, say "No documented rationale — likely agent default."
**Alternatives considered:** 2-3 real alternatives with pros/cons.
**Trade-offs:** What we gain, what we lose.
**At scale (50 clients):** Does this hold, strain, or break?
**Recommendation:** KEEP / CHANGE / INVESTIGATE FURTHER
**Evidence:** Links to code, config files, docs, or external references.
```

---

## Context

This system was built fast using AI agents across Phase 1 and Phase 2. It works. Three environments are live. But most architectural decisions were made by the agent during build without independent research or recorded reasoning.

Some decisions ARE documented. Do not re-audit these — they already have rationale:

- Single container architecture (Phase 1 decisions log)
- MCP over custom integration (Phase 1 decisions log)
- Dual auth strategy (Phase 1 decisions log)
- Connection pooling config — ADR-012
- Cold start policy — ADR-010
- DB-backed auth tokens — ADR-011
- Tenant isolation model — ADR-013
- Secrets management — ADR-014
- OAuth hardening — ADR-015
- Data sovereignty position — ADR-009

**Your job is the gaps.** Focus only on decisions with NO or PARTIAL documented rationale.

---

## Zero Rationale — Priority

These have no documented reasoning anywhere. Answer all of them.

1. **Why Container Apps over App Service, AKS, or Azure Functions?** The decision to reject microservices is documented, but not why Container Apps was the specific choice for the single-container model. What does Container Apps give us that App Service doesn't? Where does it fall short vs AKS?

2. **Why FastAPI over Django, Flask, or other Python frameworks?** Is this the right framework for a system serving both REST API and MCP? What are the scaling characteristics?

3. **Why SQLAlchemy over raw pyodbc or another ORM?** We use SQLAlchemy with Azure SQL. Is this the standard pairing? What overhead does the ORM add? Is raw pyodbc better for this use case?

4. **Why Azure SQL Basic tier?** What's the DTU ceiling? What happens when a client has a busy day — 50 meetings in a week, bulk action creation, heavy search? Where does Basic tier break and what does the next tier cost?

5. **Why React 18 for a mostly read-only web UI?** The web UI is primarily a dashboard for viewing meetings, actions, and decisions. Is React 18 the right choice, or is this over-engineered? Would a simpler approach (server-rendered, HTMX, even static) be more appropriate?

6. **Why MSAL React + fastapi-azure-auth?** Is this the standard, recommended approach for Azure AD auth with FastAPI + React? Or was this an agent pick? What does Microsoft actually recommend?

7. **Why SHA256 single-hash for MCP tokens?** The token auth uses `plaintext → SHA256 → compare`. Is single-round SHA256 sufficient for auth tokens, or should this be bcrypt/argon2/scrypt? What's the threat model — if the database leaks, can tokens be reversed?

8. **Why stateless JWTs for OAuth access/refresh tokens?** No revocation mechanism exists. Refresh tokens last 30 days. If a token is compromised, there's no way to invalidate it. Is this acceptable? What's the standard approach for MCP OAuth?

9. **Why 16 MCP tools with this specific split?** 7 action tools, 6 meeting tools, 3 decision tools. Is this right-sized? Are any tools redundant? Are any missing? Compare against what Claude and ChatGPT can actually make use of effectively.

10. **Why App Insights only on team environment?** Marshall (paying client) and demo have no telemetry. Why? Is this a cost decision, an oversight, or intentional? What does it cost to add App Insights to all environments?

11. **Why $100 AUD budget alert threshold?** Where did this number come from? Is it based on expected cost or arbitrary? What should it actually be based on current per-environment costs?

12. **Why both SSE and Streamable HTTP transports?** SSE is for Claude Desktop, Streamable HTTP is for ChatGPT/Copilot. Does Claude Desktop still require SSE, or has the MCP spec moved on? Can we consolidate to one transport?

13. **Why ALLOWED_USERS as CSV environment variable?** User allowlist is a comma-separated env var. At 50 clients, this becomes unmaintainable. Why not a database table? What's the migration path?

14. **What's the base container image?** What Docker base image are we using? Has it been scanned for CVEs? When was it last updated? What's our update policy?

15. **Are dependencies pinned to exact versions?** Check both `requirements.txt` (Python) and `package.json` (Node). Are we using exact pins (`==`, no `^` or `>=`)? What happens if a transitive dependency pushes a breaking change?

16. **What's the MCP SDK versioning strategy?** We depend on `mcp[cli] >=1.8.0`. The MCP spec is still evolving. What happens when the spec changes? Do we have a strategy for SDK upgrades, or are we just hoping nothing breaks?

---

## Partial Rationale — Secondary

These have some documentation but are missing the "why this specifically?" answer.

17. **Why OAuth 2.1 specifically?** The hardening work is well-documented (ADR-015), but not why we went with full OAuth 2.1 + PKCE over a simpler token exchange. ChatGPT requires OAuth — but does it require 2.1? What does 2.1 give us over 2.0?

18. **Why this Bicep module decomposition?** The module structure is documented (container-app, sql, key-vault, monitoring, budget modules). But why this split? Is it the right decomposition for stamping new environments? What would need to change at 50 clients?

19. **Why in-memory auth codes for OAuth?** The trade-off is acknowledged (codes lost on restart), but is this acceptable at scale? If two replicas are running, auth codes created on replica A won't exist on replica B. Is this a problem?

20. **Why 1MB payload limit?** Pydantic validation caps payloads at 1MB. Why 1MB and not 512KB or 10MB? What's the largest realistic payload (a meeting with a full transcript)? Is 1MB sufficient or too generous?

---

## Operational Questions — Must Answer Before Scaling

These aren't code decisions — they're operational gaps. Answer each with what exists today and what's needed.

21. **Database migrations at scale.** How do we apply schema changes across 50 client databases? There's no migration framework. `002_client_tokens.sql` was run manually on each database. What's the plan when we need `003_something.sql` across 50 instances?

22. **Code update rollout.** How do we roll out a code update to all client environments? What if the update works for 49 clients but breaks one? Is there a rollback mechanism?

23. **Secrets rotation.** Can we rotate `JWT_SECRET` without breaking existing OAuth tokens? What's the rotation procedure? Has it ever been tested?

24. **Client offboarding.** What happens when a client leaves? Can we export their data? Delete it? What's the teardown process? Currently none exists.

25. **Data retention under NZ Privacy Act.** What's our position? Can a client request deletion of all their data? How would we fulfil that request? What data persists in backups after deletion?

26. **Backup RPO/RTO.** What recovery point and recovery time are we committing to? E1 tested PITR with 7-day retention. But what if Australia East goes down entirely? Is there a geo-redundancy story?

27. **Performance baselines.** What does "normal" look like? Average response time for an MCP tool call? Database query time? Container CPU/memory usage? Without baselines, we can't detect degradation.

28. **Incident response.** If the system goes down at 2am, who gets notified? Currently: nobody. There are budget alerts but no health alerts. No incident response playbook. What's needed?

29. **Per-user MCP attribution.** All MCP calls currently log as `system@generationai.co.nz` (hardcoded in `mcp_server.py:33`). Can we trace activity back to the actual user? What would that require?

---

## Deliverables

Three files in `2-build/`:

1. `d13-zero-rationale-audit.md` — Items 1-16
2. `d13-partial-rationale-audit.md` — Items 17-20
3. `d13-operational-audit.md` — Items 21-29

**For each item:** Follow the output format above. Be honest. If something was an agent default with no research behind it, say so. If something is the right choice, explain why with evidence. If something needs to change, say what and why.

**Do not implement fixes.** This is an audit only. Fixes come in D16 after research.

---

## STEP 0: Preflight Check (Run This First)

Before starting the audit, confirm you can access everything you need. Output a short preflight report:

```
## Preflight Report

### File Access
- [ ] server/src/main.py — found / not found
- [ ] server/src/mcp_server.py — found / not found
- [ ] server/src/api.py — found / not found
- [ ] server/src/oauth.py — found / not found
- [ ] server/src/config.py — found / not found
- [ ] server/src/database.py — found / not found
- [ ] server/requirements.txt — found / not found
- [ ] web/package.json — found / not found
- [ ] Dockerfile — found / not found
- [ ] infra/*.bicep — list all found
- [ ] infra/*.bicepparam — list all found
- [ ] infra/deploy-bicep.sh — found / not found
- [ ] CLAUDE.md — found / not found

### Existing Decision Docs
- [ ] 2-build/mi-decisions-phase1.md — found / not found
- [ ] 2-build/mi-decisions-phase2.md — found / not found
- [ ] 3-delivery/adr-009*.md through adr-015*.md — list all found

### Quick Spot Checks
- [ ] Can you read the Dockerfile base image? (Report what it is)
- [ ] Can you read requirements.txt dependency pins? (Report format: ==, >=, ^, or mixed)
- [ ] Can you find ALLOWED_USERS in config.py? (Report how it's loaded)
- [ ] Can you find the SHA256 hashing in the codebase? (Report file and line)
- [ ] Can you find the `system@generationai.co.nz` hardcode? (Report file and line)
- [ ] Can you read Bicep module structure? (Report module count)
- [ ] What's the budget alert threshold you can see in Bicep? (Report value and currency)

### Assumptions Check
Confirm or correct these assumptions from the brief:
- [ ] MCP tools: we claim 16 (7 action, 6 meeting, 3 decision). Count actual tools.
- [ ] OAuth: we claim stateless JWTs with 30-day refresh. Confirm from code.
- [ ] Payload limit: we claim 1MB Pydantic validation. Confirm from code.
- [ ] Transports: we claim both SSE and Streamable HTTP. Confirm from code.

### Blockers
List anything you cannot access or that doesn't match what the brief assumes.
If blockers exist, STOP and report back before proceeding to the audit.
```

**Do not start the audit until the preflight is clean.** If any file is missing, any assumption is wrong, or any path doesn't resolve — report back first so we can correct the brief.

---

## Files to Examine

Start here. This is not exhaustive — follow the code wherever the questions lead.

- `server/src/main.py` — Entry point, transport setup
- `server/src/mcp_server.py` — MCP tool definitions, user attribution
- `server/src/api.py` — REST API
- `server/src/oauth.py` — OAuth 2.1 implementation
- `server/src/config.py` — Environment config, ALLOWED_USERS
- `server/src/database.py` — SQLAlchemy setup, connection pooling
- `server/requirements.txt` — Python dependencies
- `web/package.json` — Node dependencies
- `Dockerfile` — Base image, build steps
- `infra/*.bicep` — Infrastructure modules
- `infra/*.bicepparam` — Environment configs
- `infra/deploy-bicep.sh` — Deployment script
- `CLAUDE.md` — Agent context doc
- `2-build/mi-decisions-phase1.md` — Existing Phase 1 decisions
- `2-build/mi-decisions-phase2.md` — Existing Phase 2 decisions (if exists)
- `3-delivery/adr-*.md` — ADRs 009-015

---

*Brief prepared by: Caleb Lucas / Claude — 12 February 2026*

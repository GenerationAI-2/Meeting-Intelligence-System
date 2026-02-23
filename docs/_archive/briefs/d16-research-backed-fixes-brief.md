# D16: Research-Backed Fixes — Agent Brief

**Project:** Meeting Intelligence System — Phase 3
**Task:** Research and implement fixes for D13/D14/D15 findings
**Owner:** Repo Agent
**Date:** 12 February 2026
**Depends on:** D13 (complete), D14 (complete), D15 (complete), D13 Quick Fixes (complete)

---

## Objective

Fix everything flagged across D13, D14, and D15. Every fix must be researched before implemented. No more "agent picks the approach."

**For each fix, document:**

```
## [Fix Title]

**Finding:** Which D13/D14/D15 item(s) this addresses.
**Problem:** What's wrong, in plain language.
**Research:**
- Option A: [approach] — pros, cons, effort
- Option B: [approach] — pros, cons, effort
- Option C: [approach] — pros, cons, effort (if applicable)
**Sources:** Links to docs, RFCs, specs, or examples consulted.
**Chosen approach:** Which option and why.
**Implementation:** What was changed (files, lines).
**Verification:** How it was tested. Evidence it works.
**Commit:** Commit hash and message.
```

**Rules:**
- One commit per fix. Clear commit messages referencing the D-item number.
- Run existing tests after each fix.
- Test on team environment only. Do not touch Marshall or demo.
- If a fix requires infrastructure changes (Bicep), note it but don't deploy to Marshall/demo. Team only.
- If research reveals the fix is more complex than expected, STOP and report back before implementing.

---

## Batch 1: Quick Hardening (do these first, in order)

These are small, well-understood fixes. Research is light — confirm the approach, implement, verify.

### 1.1 — Dockerfile Non-Root User
**Findings:** D14 6c (HIGH), D15 SE:08 (HIGH), D15 Azure Baseline (HIGH)
**Scope:** Add a non-root `USER` directive to `server/Dockerfile`. Create a dedicated app user. Ensure the application still starts and serves correctly.
**Research:** What user/group convention do Python container best practices recommend? Does the app need write access to any directory?
**Verify:** Rebuild. Confirm container starts. Confirm `whoami` inside container is NOT root. Run MCP tool call to confirm functionality.

### 1.2 — Origin Header Validation + DNS Rebinding Protection
**Findings:** D15 MCP Spec gap #23 (HIGH)
**Scope:** The MCP SDK's `TransportSecuritySettings` has `enable_dns_rebinding_protection=False` explicitly. Enable it. Validate Origin header on incoming requests.
**Research:** What does the MCP spec (2025-11-25) require for Origin validation? What does the Python MCP SDK provide out of the box? Is enabling the flag sufficient, or do we need custom middleware?
**Verify:** Send a request with a spoofed Origin header. Confirm it's rejected. Send a legitimate request. Confirm it works.

### 1.3 — CORS Restriction
**Findings:** D15 OWASP API8 (MEDIUM)
**Scope:** Replace `allow_methods=["*"]` and `allow_headers=["*"]` with the specific methods and headers the API actually uses.
**Research:** What HTTP methods does the API use? (GET, POST, PUT, DELETE — confirm from code.) What headers are needed? (Authorization, Content-Type — confirm from code.)
**Verify:** Web UI still works. MCP still works. CORS preflight returns only the specified methods/headers.

### 1.4 — Security Headers Middleware
**Findings:** D15 SE:06 (MEDIUM), D15 OWASP API8 (MEDIUM)
**Scope:** Add middleware that sets security headers on all responses: `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
**Research:** What are the recommended values for a FastAPI API + React SPA? Does HSTS need a specific `max-age`? Does CSP need to allow React's inline styles?
**Verify:** Confirm headers present on API responses. Confirm web UI still renders correctly (CSP not blocking anything).

### 1.5 — OAuth client_secret Hashing
**Findings:** D15 Azure Baseline IM-8 (MEDIUM)
**Scope:** OAuth `client_secret` is stored in plain text in the `OAuthClient` table. Hash it with SHA256 (same approach as MCP tokens — consistent pattern). Update the token endpoint to compare against the hash.
**Research:** Is SHA256 appropriate here? (Yes — same reasoning as D13 #7: high-entropy random secret, not a password.) Confirm the OAuth token exchange flow still works after hashing.
**Verify:** Register a new OAuth client. Confirm `client_secret` in database is hashed, not plain text. Confirm token exchange still works with the original secret.

### 1.6 — OAuth State Parameter Validation
**Findings:** D15 OAuth 2.1 (MEDIUM)
**Scope:** The consent form accepts a `state` parameter and forwards it, but doesn't generate or validate it server-side. This leaves the flow open to CSRF.
**Research:** What does OAuth 2.1 require for state? Should the server generate state, or is that the client's responsibility? (In standard OAuth, the client generates and validates state. But our consent page is server-rendered — check what the MCP spec expects.)
**Verify:** Confirm the consent flow works with a state parameter. Confirm requests without state or with tampered state are handled correctly per spec.

### 1.7 — XSS Server-Side Sanitisation
**Findings:** D14 4c (MEDIUM), D15 SE:06 (MEDIUM)
**Scope:** XSS payloads stored verbatim in database. Currently relying entirely on React escaping. Add server-side sanitisation or output encoding at the API layer.
**Research:** Two approaches: (A) sanitise on input (strip HTML tags before storing), or (B) escape on output (encode HTML entities in API responses). Which is standard practice for an API that serves both a web UI and MCP clients? What does OWASP recommend?
**Verify:** Store a `<script>alert('xss')</script>` payload. Retrieve via API. Confirm it's sanitised/escaped. Confirm legitimate text with angle brackets (e.g. `meeting < 30 mins`) still works.

### 1.8 — Null Byte Input Validation
**Findings:** D14 4d-ii (LOW)
**Scope:** Null bytes (`\x00`) accepted and stored in text fields. Strip or reject them.
**Research:** Should we strip null bytes silently or reject the request with a 400? What does Pydantic recommend for string validation?
**Verify:** Send a payload with null bytes. Confirm it's rejected or stripped. Confirm normal text still works.

---

## Batch 2: OAuth + Token Engineering (do these together — they're interconnected)

These are the substantive engineering fixes. Research thoroughly before implementing.

### 2.1 — JWT Dual-Key Rotation Support
**Findings:** D13 #23 (HIGH), D14 6a (HIGH), D15 SE:09 (HIGH)
**Scope:** Currently, rotating `JWT_SECRET` instantly invalidates all OAuth tokens. Implement dual-key support: accept tokens signed with either the current or previous secret during a transition window.
**Research:**
- How do production systems handle JWT key rotation? (Key ID `kid` header + JWKS? Dual-secret with fallback? Time-windowed rotation?)
- What's the simplest approach that works with our stateless JWT model?
- How long should the transition window be? (Must cover the 30-day refresh token lifetime.)
- Does this require a second Key Vault secret, or an env var for the old key?
**Constraint:** This must work with the existing ChatGPT OAuth flow. Test the full flow: authorise → get tokens → rotate secret → use refresh token → confirm it still works with the old-key fallback.

### 2.2 — Refresh Token Rotation on Use
**Findings:** D15 OAuth 2.1 (HIGH), D15 MCP Spec (HIGH)
**Scope:** OAuth 2.1 mandates that refresh tokens for public clients (ChatGPT) are rotated on each use. Currently, the same refresh token is valid for 30 days with no rotation.
**Research:**
- What does "rotation" mean in practice? (Issue a new refresh token on each `/oauth/token` call with `grant_type=refresh_token`. Invalidate the old one.)
- Does this require database-backed refresh tokens? (Currently stateless JWTs — rotation requires tracking which tokens have been used.)
- What's the interaction with dual-key rotation from 2.1?
- Does ChatGPT handle receiving new refresh tokens on each exchange?
**Constraint:** This is the biggest change in D16. If research reveals it requires moving from stateless to database-backed tokens, document the full design and STOP. Report back before implementing.

### 2.3 — Token Revocation Endpoint
**Findings:** D13 #8 (MEDIUM), D15 OAuth 2.1 (MEDIUM)
**Scope:** No `/oauth/revoke` endpoint exists. With 30-day refresh tokens, a compromised token can't be invalidated.
**Research:**
- What does RFC 7009 (Token Revocation) require?
- Does the MCP spec require a revocation endpoint?
- If we implement refresh token rotation (2.2), does revocation become less critical? (A rotated token is already single-use.)
- Implementation: blacklist table? Or does DB-backed tokens from 2.2 make this trivial?
**Constraint:** Depends on the design from 2.2. If 2.2 moves to DB-backed tokens, revocation is just a DELETE. If we stay stateless, revocation needs a blacklist.

### 2.4 — RFC 9728: Protected Resource Metadata
**Findings:** D15 MCP Spec (HIGH)
**Scope:** MCP spec 2025-11-25 requires servers to implement OAuth 2.0 Protected Resource Metadata (RFC 9728). We don't.
**Research:**
- What does RFC 9728 require? (A `/.well-known/oauth-protected-resource` endpoint that describes the resource server's auth requirements.)
- What fields are mandatory?
- Does the Python MCP SDK provide helpers for this?
- What does the MCP spec specifically require beyond the base RFC?
**Verify:** Endpoint responds with correct metadata. Claude Desktop and ChatGPT can discover auth requirements from it.

### 2.5 — MCP-Protocol-Version Header Validation
**Findings:** D15 MCP Spec (MEDIUM)
**Scope:** Server doesn't validate the `MCP-Protocol-Version` header. Spec requires server to reject invalid versions with 400.
**Research:** What versions should we accept? Just current, or a range? What does the MCP SDK provide?
**Verify:** Request without header → rejected. Request with valid version → accepted. Request with invalid version → rejected with 400.

### 2.6 — RFC 8707: Resource Indicators
**Findings:** D15 MCP Spec (MEDIUM)
**Scope:** Clients should include a `resource` parameter in auth/token requests. Server doesn't validate it.
**Research:** What does the MCP spec require for Resource Indicators? Is this a MUST or SHOULD? Does the Python MCP SDK handle this? What's the interaction with RFC 9728 (2.4)?
**Verify:** Auth flow works with resource parameter. Tokens are bound to the correct resource.

---

## Batch 3: Rate Limiting + Monitoring (independent of Batch 2)

### 3.1 — Rate Limiting
**Findings:** D15 OWASP API4 (HIGH), D15 OWASP API2 (HIGH)
**Scope:** No rate limiting on any endpoint. An attacker with a valid token could overwhelm the system.
**Research:**
- What's the right approach for FastAPI? (`slowapi`? Custom middleware? Azure API Management?)
- What limits are appropriate? Per-IP? Per-token? Per-client?
- Should MCP endpoints and REST endpoints have different limits?
- What about the OAuth endpoints — stricter limits for auth to prevent brute force?
- What does Azure Container Apps provide natively?
**Constraint:** Rate limiting must not break legitimate MCP usage (Claude/ChatGPT making rapid sequential tool calls).

### 3.2 — Security Alert Rules
**Findings:** D15 Azure Baseline LT-2 (HIGH), D13 #28 (HIGH)
**Scope:** No Azure Monitor alerts. System could be down for hours unnoticed.
**Research:** What alerts does Microsoft recommend for Container Apps? Minimum set:
- Container health probe failures
- HTTP 5xx error rate spike
- Response time degradation (>2x baseline from D14)
- Auth failure rate spike (brute force indicator)
- Container restart count
**Implementation:** Azure Monitor alert rules via Bicep. Where should notifications go? (Email? Webhook? Teams channel?)
**Constraint:** Add to Bicep templates so new environments get alerts automatically. Deploy to team for testing.

### 3.3 — Vulnerability Scanning in Pipeline
**Findings:** D14 6b/6c (MEDIUM), D15 Azure Baseline PV-2 (MEDIUM)
**Scope:** No automated vulnerability scanning. D14 ran manual pip-audit and Trivy. Automate it.
**Research:** What's the simplest way to add scanning without a full CI/CD pipeline? Options:
- Pre-commit hook running pip-audit + npm audit
- GitHub Actions workflow (if repo is on GitHub)
- Script that runs before deploy-bicep.sh
**Constraint:** We don't have CI/CD yet (that's a separate item). Find the simplest automation that works with current manual deployment.

---

## Batch 4: Operational Foundations

### 4.1 — Database Migration Framework
**Findings:** D13 #21 (HIGH operational)
**Scope:** No way to apply schema changes across multiple client databases. Manual SQL execution today.
**Research:**
- Alembic (SQLAlchemy's migration tool) vs custom runner vs Flyway?
- How do multi-tenant systems handle per-database migrations?
- Do we need a migrations tracking table per database?
**Constraint:** Must work across N client databases. Design for 50, test with team/demo.

### 4.2 — Multi-Client Deploy Script
**Findings:** D13 #22 (HIGH operational)
**Scope:** Currently must run `deploy-bicep.sh` once per environment manually.
**Research:** Script that:
- Reads list of environments from a config file
- Deploys to internal environments first (team)
- Health-checks after each deployment
- Stages client rollouts (one at a time, then batch)
- Stops on failure with rollback option
**Constraint:** Build and test with team/demo only. Do not deploy to Marshall until reviewed.

### 4.3 — Incident Response Playbook
**Findings:** D13 #28 (HIGH), D15 SE:12 (HIGH), D15 OE:08 (HIGH)
**Scope:** Document, not code. Create `3-delivery/incident-response-playbook.md`.
**Contents:**
- Alert types and severity levels
- Who gets notified (currently: Caleb and Mark)
- Response procedures per alert type
- Escalation path
- Client communication template
- Post-incident review process
**Constraint:** Keep it simple. This is a 1-3 person operation, not enterprise ITIL.

### 4.4 — Client Offboarding Runbook
**Findings:** D13 #24 (operational)
**Scope:** Document + script. What happens when a client leaves?
**Contents:**
- Data export procedure (script to dump client DB to JSON/CSV)
- Verification step (client confirms they have their data)
- Resource teardown (delete resource group, revoke tokens, remove from ALLOWED_USERS)
- Confirmation checklist
**Constraint:** Build the export script. Test against team environment. Document the manual steps.

### 4.5 — SLA / RPO / RTO Documentation
**Findings:** D15 RE:01 (MEDIUM), D13 #26 (operational)
**Scope:** Document. Define what we commit to.
**Suggested targets (to be confirmed by Caleb):**
- Availability: 99.5% (allows ~3.6 hours downtime/month)
- RPO: 15 minutes (Azure SQL PITR)
- RTO: 30 minutes (redeploy from Bicep)
- Support hours: NZ business hours
**Constraint:** Document only. These become part of the client agreement.

---

## Out of Scope for D16 (LATER)

These were flagged in D15 but are not worth fixing now:

- **VNet / private endpoints** — significant infrastructure change, enterprise requirement
- **Microsoft Defender for Containers** — $7/month per cluster, assess when we have 10+ clients
- **Signed container images** — nice-to-have, no immediate risk
- **Conditional access policies** — Entra ID feature, assess per-client
- **Sequential IDs → UUIDs** — breaking change to database schema, low actual risk with tenant isolation
- **IaC template scanning (Checkov)** — add when CI/CD pipeline exists
- **PII scrubbing in telemetry** — assess when data retention policy is finalised
- **Consolidated SQL Servers** — architectural change, assess at 10+ clients
- **Full CI/CD pipeline** — larger initiative, assess after D16

---

## Order of Operations

```
Batch 1 (1.1 → 1.8)  — Sequential. Each commit independent.
    ↓
Batch 2 (2.1 → 2.6)  — Sequential. 2.1 before 2.2. 2.2 before 2.3. 2.4-2.6 independent.
    ↓
Batch 3 (3.1 → 3.3)  — Can run in parallel with Batch 2 (independent code areas).
    ↓
Batch 4 (4.1 → 4.5)  — Can start after Batch 1. Mix of code and documentation.
```

**Checkpoint after Batch 2:** Report back before starting Batch 3. The OAuth/token work is the riskiest area. We want to review before moving on.

---

## Deliverables

1. `d16-fix-log.md` in `2-build/` — One entry per fix using the output format above.
2. Individual commits per fix with clear messages.
3. All tests passing after each batch.
4. Checkpoint report after Batch 2 (before proceeding to Batch 3).
5. Operational documents in `3-delivery/` for items 4.3, 4.4, 4.5.

---

*Brief prepared by: Caleb Lucas / Claude — 12 February 2026*

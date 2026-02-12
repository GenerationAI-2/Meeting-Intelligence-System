# D15: Best Practice Comparison — Agent Brief

**Project:** Meeting Intelligence System — Phase 3
**Task:** Compare current build against established standards
**Owner:** Repo Agent
**Date:** 12 February 2026
**Depends on:** D13 Build Rationale Audit (complete), D14 Stress Testing (complete)

---

## Objective

Compare the current system against five established standards. For each standard, identify where we comply, where we don't, and whether the gap matters at our scale (1-3 clients now, 50 target).

D13 told us what we built and why. D14 told us what breaks under stress. D15 tells us what we're missing compared to what the industry says we should have.

**This is a comparison task, not a fix task.** Document gaps. Don't fix anything. Fixes come in D16.

**Output format:** For each standard, use this structure:

```
## [Standard Name]

**Source:** URL or document reference
**Version/Date:** Which version of the standard was used

### Compliant
| Requirement | How We Meet It | Evidence |
|------------|----------------|----------|
| ... | ... | file:line or config reference |

### Non-Compliant
| Requirement | Gap | Severity | Matters at 50 Clients? |
|------------|-----|----------|----------------------|
| ... | ... | HIGH/MEDIUM/LOW | Yes/No + why |

### Not Applicable
| Requirement | Why N/A |
|------------|---------|
| ... | ... |
```

---

## Context From D13 + D14

You already have detailed findings. Don't re-test — reference them. Key findings to build on:

**D13 confirmed:**
- Container Apps is the right choice (item 1 — KEEP)
- FastAPI is correct for MCP + REST (item 2 — KEEP)
- SHA256 is appropriate for random tokens (item 7 — KEEP)
- Stateless JWTs need revocation at scale (item 8 — INVESTIGATE)
- ALLOWED_USERS as env var is adequate short-term (item 13 — INVESTIGATE)

**D14 confirmed:**
- Auth is tight — all bypass attempts blocked (tests 3a-3d)
- SQL injection fully blocked by parameterised queries (test 4b)
- XSS payloads stored verbatim, relying on React escaping (test 4c — MEDIUM)
- Container runs as root (Trivy DS-0002 — HIGH)
- JWT rotation breaks all OAuth instantly (test 6a — HIGH)
- Zero downtime deployment confirmed (tests 7a, 7b)
- Performance holds at 50 concurrent, 500 meetings (tests 1b, 5a)

---

## STEP 0: Preflight

```
## Preflight

- [ ] Can you access the MCP specification? (https://spec.modelcontextprotocol.io or local docs)
- [ ] Can you access the OAuth 2.1 draft RFC? (RFC 9728 / draft-ietf-oauth-v2-1)
- [ ] Can you access the OWASP API Security Top 10? (2023 version)
- [ ] Can you access Azure Well-Architected Framework docs? (Microsoft Learn)
- [ ] Can you access Azure security baseline for Container Apps? (Microsoft Learn)
- [ ] Do you have access to the D13 audit files? (2-build/d13-*.md)
- [ ] Do you have access to the D14 stress test results? (2-build/d14-stress-test-results.md)

### Blockers
If you cannot access any standard, note it and compare against what you can access.
Do NOT skip a standard — use your training knowledge of the standard if the URL is inaccessible, but note this limitation.
```

---

## Standard 1: Azure Well-Architected Framework

**Source:** https://learn.microsoft.com/en-us/azure/well-architected/

Compare across all five pillars:

**Reliability:**
- Do we have health probes? (yes — live/ready split)
- Do we have retry logic? (yes — exponential backoff, 13 error codes)
- Do we have redundancy? (single region, no geo-redundancy)
- What's our recovery story? (PITR 7-day, no geo-failover)
- Do we have chaos/failure testing? (D14 tested some — reference results)

**Security:**
- Identity management (Entra ID + MCP tokens + OAuth)
- Network security (no WAF, no VNet, no private endpoints)
- Data protection (encryption at rest via Azure SQL, TLS in transit)
- Container security (running as root — D14 finding)
- Secret management (Key Vault for JWT_SECRET + App Insights)

**Cost Optimisation:**
- Scale-to-zero working? (yes, 209ms cold start from D14)
- Right-sized resources? (Basic tier adequate per D14 load tests)
- Budget alerts? (yes, $35 threshold after D13 quick fix)
- Cost per client? (~$11-15/month per D13)

**Operational Excellence:**
- IaC coverage? (Bicep for all infra)
- Deployment automation? (deploy-bicep.sh, 97s deployment per D14)
- Monitoring? (App Insights — but verify coverage across environments)
- Incident response? (none — D13 item 28)
- Runbooks? (none)

**Performance Efficiency:**
- Baselines established? (yes, from D14 — 183ms P50)
- Auto-scaling configured? (scale-to-zero, max replicas?)
- Connection pooling? (yes, QueuePool size=5, overflow=15)
- Caching? (none — is any needed?)

---

## Standard 2: MCP Specification Compliance

**Source:** https://spec.modelcontextprotocol.io (use latest stable version)

Check:

**Transport:**
- SSE transport — does our implementation match the spec?
- Streamable HTTP transport — does our implementation match the spec?
- Are there any spec requirements we don't implement?
- Has the spec deprecated SSE yet? What's the migration timeline?

**Tools:**
- Do our 16 tool definitions follow the spec format? (name, description, inputSchema)
- Are tool responses in the correct format?
- Are error responses spec-compliant?

**Authentication:**
- Does our OAuth implementation match MCP's auth requirements?
- Dynamic Client Registration — do we implement it per spec?
- Token endpoint — spec-compliant?
- Are there any MCP-specific auth requirements beyond standard OAuth?

**Protocol:**
- JSON-RPC 2.0 compliance
- Capability negotiation
- Session management
- Any spec features we don't implement that we should?

---

## Standard 3: OAuth 2.1 Compliance

**Source:** RFC 9728 / IETF OAuth 2.1 draft (use latest)

Check:

**Core flow:**
- Authorization code grant with PKCE — compliant?
- S256 code challenge method — enforced?
- Refresh token rotation — do we rotate on use?
- Token lifetimes — reasonable? (1hr access, 30d refresh per D13)

**Security requirements:**
- HTTPS enforcement
- State parameter for CSRF protection
- Redirect URI exact matching
- No implicit grant (should be absent)
- No resource owner password grant (should be absent)
- Bearer token usage in Authorization header

**What 2.1 adds over 2.0:**
- PKCE mandatory (not optional) — do we enforce?
- Refresh token rotation or sender-constrained tokens — do we implement?
- Exact redirect URI matching (no wildcards) — do we enforce?

**Known gaps from D13/D14:**
- No token revocation endpoint (D13 item 8)
- No refresh token rotation on use (if applicable)
- In-memory auth codes lost on restart (D14 test 2c)

---

## Standard 4: OWASP API Security Top 10 (2023)

**Source:** https://owasp.org/API-Security/editions/2023/en/0x11-t10/

Check each of the 10 risks:

1. **API1:2023 — Broken Object Level Authorisation:** Can a user access another user's meetings/actions/decisions by guessing IDs? (D14 tested cross-tenant — but test within a single tenant too)

2. **API2:2023 — Broken Authentication:** D14 tested extensively. Reference results. Any gaps?

3. **API3:2023 — Broken Object Property Level Authorisation:** Can users modify fields they shouldn't? Are there admin-only fields exposed?

4. **API4:2023 — Unrestricted Resource Consumption:** No rate limiting exists. What's the risk? What does OWASP recommend?

5. **API5:2023 — Broken Function Level Authorisation:** Are any admin/system functions accessible to regular users?

6. **API6:2023 — Unrestricted Access to Sensitive Business Flows:** Are there business flows that could be abused through automation?

7. **API7:2023 — Server Side Request Forgery (SSRF):** Does the API make outbound requests based on user input? (Probably not — but verify)

8. **API8:2023 — Security Misconfiguration:** CORS settings? Debug mode? Default credentials? Verbose errors? (D14 tested error responses — reference)

9. **API9:2023 — Improper Inventory Management:** Do we have API documentation? OpenAPI spec? Are there undocumented endpoints?

10. **API10:2023 — Unsafe Consumption of APIs:** Do we call external APIs? (Fireflies was removed — but check for any remaining external calls)

---

## Standard 5: Azure Security Baseline for Container Apps

**Source:** https://learn.microsoft.com/en-us/security/benchmark/azure/baselines/azure-container-apps-security-baseline

Check Microsoft's recommended controls:

**Network Security:**
- VNet integration
- Network Security Groups
- Private endpoints
- WAF / DDoS protection

**Identity Management:**
- Managed identity usage
- Conditional access
- Service principal least privilege

**Data Protection:**
- Encryption at rest
- Encryption in transit
- Key management

**Logging and Monitoring:**
- Diagnostic settings enabled?
- Log Analytics workspace?
- Security alerts configured?
- Microsoft Defender for Containers?

**Container Security:**
- Non-root user (known gap — D14 HIGH finding)
- Image scanning in pipeline
- Signed images
- Resource limits (CPU/memory)
- Read-only filesystem where possible

**Posture and Vulnerability Management:**
- Regular patching cadence
- Dependency scanning
- Infrastructure scanning

---

## Deliverables

One file in `2-build/`:

1. `d15-best-practice-comparison.md` — All five standards, using the output format above.

**End with a "Gap Summary" section** that consolidates all non-compliant findings across all five standards, deduplicated, ranked by severity. Cross-reference D13 and D14 findings where they overlap — don't list the same gap twice, just note it's confirmed by multiple sources.

Final table format:

```
| # | Gap | Standard(s) | Severity | D13/D14 Reference | New Finding? |
|---|-----|-------------|----------|-------------------|-------------|
| 1 | ... | ... | ... | D13 #8 / D14 6a | No |
| 2 | ... | OWASP API4 | HIGH | — | Yes |
```

---

## Constraints

- **Compare, don't fix.** Fixes come in D16.
- **Reference D13 and D14 findings** rather than re-testing. If a standard checks something we already tested, cite the result.
- **Be specific about versions.** Note which version of each standard you compared against.
- **Flag anything new.** If a standard reveals a gap that D13 and D14 didn't catch, call it out clearly.

---

*Brief prepared by: Caleb Lucas / Claude — 12 February 2026*

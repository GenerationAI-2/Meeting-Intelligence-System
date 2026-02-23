# D14: Stress Testing — Agent Brief

**Project:** Meeting Intelligence System — Phase 3
**Task:** Stress Testing (Sandboxed)
**Owner:** Repo Agent
**Date:** 12 February 2026
**Depends on:** D13 Build Rationale Audit (complete), D13 Quick Fixes (in progress)

---

## Objective

Actively try to break this system. Document every finding. We need to know what fails, where the limits are, and what "normal" looks like — before we have 50 clients depending on it.

**This is a test-and-report task, not a fix task.** Document findings. Don't fix anything. Fixes come in D16 after research.

**Output format:** For each test, report:

```
## [Test Name]

**What was tested:** Description of the test.
**Method:** How it was run (script, curl command, tool, manual).
**Expected behaviour:** What should happen.
**Actual behaviour:** What actually happened.
**Evidence:** Logs, response codes, timing data, error messages.
**Severity:** CRITICAL / HIGH / MEDIUM / LOW / PASS
**Recommendation:** What this finding means for D16.
```

---

## Environment

Use the **team** environment for all testing. Do NOT test against Marshall (live client) or demo.

If any test requires infrastructure changes (e.g. scaling replicas, changing SQL tier), note it as a requirement and stop. We'll provision a dedicated test environment if needed.

---

## STEP 0: Preflight

Before running tests, confirm:

```
## Preflight

- [ ] Team environment is accessible and responding
- [ ] You can authenticate via MCP (token auth)
- [ ] You can authenticate via OAuth (JWT)
- [ ] You can authenticate via Web UI (Entra ID)
- [ ] You can read App Insights / container logs for team environment
- [ ] You have baseline response time for one MCP tool call (measure `list_meetings`)
- [ ] You have baseline response time for one REST API call (measure `GET /api/meetings`)
- [ ] Existing test suite passes (run `pytest` — report count and any failures)

### Blockers
If any of the above fail, STOP and report back.
```

---

## Test Group 1: Load

Establish what "normal" looks like, then push past it.

**1a. Baseline performance**
Measure 10 sequential calls for each:
- `list_meetings` (MCP)
- `GET /api/meetings` (REST)
- `search_meetings` with keyword (MCP)
- `create_meeting` then `delete_meeting` (MCP write path)

Record: P50, P95, P99 response times. CPU and memory if observable via App Insights.

**1b. Concurrent MCP connections**
Simulate 10, 25, 50 concurrent MCP tool calls (`list_meetings`). Use async Python script or equivalent.
- At what concurrency does response time degrade >2x baseline?
- At what concurrency do requests start failing?
- Does the connection pool hold? Check for "pool exhausted" or timeout errors.

**1c. Sustained load**
Run 100 requests over 60 seconds (mixed read/write). Does performance degrade over time? Any memory leaks? Does the container restart?

**1d. Cold start impact**
If possible, scale the container to zero (or wait for auto-scale-down). Then hit it with 5 concurrent requests.
- How long until first response?
- Do any requests fail during cold start?
- What does the client actually experience?

---

## Test Group 2: Failure Recovery

**2a. Database unavailable**
If testable: what happens when a database query fails mid-request? Does the retry logic (`retry_on_transient`) actually fire? Does the error message to the client make sense, or does it leak internal details?

If you can't simulate DB failure directly, test by sending a request that would trigger a DB error (e.g. referencing a non-existent meeting ID for operations that hit the DB).

**2b. Malformed requests**
Send requests with:
- Missing required fields
- Wrong data types (string where int expected)
- Empty body
- No auth header

Confirm: Does Pydantic validation catch these cleanly? Are error responses consistent and safe (no stack traces, no internal paths)?

**2c. Container restart behaviour**
If observable: what happens to in-flight requests during a container restart? Are OAuth auth codes (in-memory) lost? This is a known gap from D13 Item #19 — confirm the behaviour.

---

## Test Group 3: Auth Bypass

**3a. No token**
Hit every MCP endpoint and every REST endpoint with no authentication header. Confirm 401 on all.

**3b. Invalid token**
Hit endpoints with:
- Garbage string as token
- Expired JWT
- JWT signed with wrong secret
- Valid JWT from a different environment (if obtainable)
- SHA256 hash of a random string as MCP token

Confirm: all return 401 or 403 with no data leakage.

**3c. Cross-tenant data access**
This system uses per-client isolated databases. But confirm: if an attacker somehow had a valid token for client A's environment, could they access client B's data? (Answer should be "impossible — different infrastructure" but verify the isolation model.)

**3d. OAuth flow abuse**
- Request an auth code with an invalid `client_id` — what happens?
- Request a token with a valid auth code twice (replay attack) — what happens?
- Request a token with an expired auth code — what happens?
- Send a token request with mismatched `redirect_uri` — what happens?
- Send a PKCE token request with wrong `code_verifier` — what happens?

---

## Test Group 4: Input Abuse

**4a. Oversized payloads**
Send payloads at: 500KB, 1MB, 2MB, 10MB, 50MB.
- Does the 1MB middleware limit catch them?
- What's the error response? Is it clean?
- Does a 50MB payload crash the container or just get rejected?

**4b. SQL injection**
Attempt SQL injection through every user-input field:
- Meeting title: `'; DROP TABLE meetings; --`
- Search query: `' OR '1'='1`
- Action text, notes, owner fields

Confirm: SQLAlchemy parameterisation blocks all attempts. No raw SQL anywhere.

**4c. Script injection (XSS)**
Store `<script>alert('xss')</script>` in:
- Meeting title
- Meeting summary
- Action text
- Decision text

Then retrieve via REST API and web UI. Confirm: content is escaped in API responses and rendered safely in React.

**4d. Unicode edge cases**
Store and retrieve:
- Emoji in meeting titles (🎯📊)
- RTL text (Arabic/Hebrew)
- Zero-width characters
- 10,000 character meeting title
- Null bytes (`\x00`)

Confirm: nothing crashes. Data round-trips correctly or is rejected cleanly.

---

## Test Group 5: Scale

**5a. Data volume**
Create 500 meetings in the team environment (script). Then:
- Does `list_meetings` still respond in <1s?
- Does `search_meetings` degrade? Measure at 100, 250, 500 meetings.
- Does the web UI paginate correctly or choke?

**5b. Azure SQL Basic tier limits**
With 500 meetings loaded:
- Run 10 concurrent search queries. Measure response times.
- Check DTU usage in Azure Portal (if accessible) or infer from response time degradation.
- At what point does Basic tier become the bottleneck?

**5c. Connection pool under sustained load**
With 500 meetings, run 25 concurrent mixed operations (reads + writes) for 60 seconds.
- Any "pool exhausted" errors?
- Any connection timeouts?
- Does `pool_pre_ping` correctly handle stale connections?

---

## Test Group 6: Secrets & Dependencies

**6a. JWT rotation test**
Document what would break if `JWT_SECRET` changed. Don't actually rotate it on team — just trace the code paths.
- Which tokens become invalid?
- Which flows break?
- What's the user impact?

If safe to test (i.e. you can restore the original secret), rotate it on team and document the actual behaviour.

**6b. Dependency audit**
Run:
- `pip audit` (or `safety check`) against Python dependencies
- `npm audit` against Node dependencies

Report: any known CVEs, severity, and whether they're exploitable in our context.

**6c. Docker image scan**
If you have access to a scanning tool (Trivy, Grype, or similar), scan the built container image. Report findings by severity.

If no scanner is available, note it as a gap and move on.

---

## Test Group 7: Update Simulation

**7a. Code deployment**
Make a trivial change (e.g. add a comment to main.py). Deploy to team using `deploy-bicep.sh`.
- How long does the deployment take?
- Is there downtime during deployment?
- What happens to active connections?
- Does the container come back healthy?

**7b. Rollback**
Revert the change. Deploy again. Confirm the system returns to its previous state cleanly.

---

## Deliverables

One file in `2-build/`:

1. `d14-stress-test-results.md` — All test groups, all results, using the output format above.

Include a summary table at the top:

```
| Test | Severity | Finding |
|------|----------|---------|
| 1a   | PASS     | Baseline: 120ms P50 |
| 3a   | PASS     | All endpoints return 401 |
| 4b   | CRITICAL | SQL injection in search field |
```

(Example only — report actual findings.)

**End with a "Top Findings" section** ranking the 5 most important results by severity, with recommendations for D16.

---

## Constraints

- **Team environment only.** Not Marshall. Not demo.
- **Document, don't fix.** If you find a vulnerability, write it up. Don't patch it.
- **Clean up after yourself.** Delete any test meetings, actions, or decisions you create. Leave the team environment in the state you found it.
- **If you need infrastructure access you don't have** (Azure Portal, App Insights, container logs), note it as a blocker and test what you can.

---

*Brief prepared by: Caleb Lucas / Claude — 12 February 2026*

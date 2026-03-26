# Comprehensive Code Review & Audit
**Date:** 27 Feb 2026

## 1. Security Audit (SQLi, Auth Bypasses, XSS, ReDoS)

### Finding 1: Silent Fail-Open to Global Admin (Legacy Mode Bypass)
*   **Severity:** Critical
*   **File:** `server/src/dependencies.py` (Line 128), `server/src/main.py` (Line 91, 175)
*   **Description:** When the application starts, if `settings.control_db_name` or the engine registry is unavailable (e.g. transient Azure connectivity issue or misconfiguration), both REST requests (`resolve_workspace`) and MCP requests (`_resolve_workspace_for_mcp`) silently fall back to `make_legacy_context(user_email)`. This context explicitly sets `is_org_admin=True` and `role="chair"`.
*   **Exploit Scenario:** If an attacker can cause the control database to be temporarily unreachable, or if a configuration deployment omits the `CONTROL_DB_NAME` environment variable, all incoming request tokens (even for low-privileged viewers) will be incorrectly assigned global admin privileges via the legacy fallback. They could then call admin endpoints or delete items.
*   **Recommended Fix:** Remove the legacy fallback entirely if the application is fully migrated. If legacy mode must be supported, it should be an explicit opt-in boolean flag (e.g., `REQUIRE_WORKSPACE_MODE=False`), not an automatic fallback upon empty DB config or connection failure.

### Finding 2: MCP Token Cache Eviction Failure on Revocation
*   **Severity:** High
*   **File:** `server/src/main.py` (Line 185)
*   **Description:** The MCP token validation uses an in-memory `_token_cache` with a 5-minute TTL (`TOKEN_CACHE_TTL = 300`). Validated tokens are cached via `token_hash`. If an admin revokes a token in the control DB, the cache is not invalidated.
*   **Exploit Scenario:** A compromised token is reported and revoked by an admin. The attacker can continue using the revoked token to access the MCP server for up to 5 minutes until the cache TTL expires.
*   **Recommended Fix:** Re-evaluate the necessity of the 5-minute cache TTL. Consider reducing it significantly (e.g., 10 seconds) or implementing a mechanism to clear the cache when a token revocation event occurs.

### Finding 3: Missing allowed_hosts Validation Leads to Origin Bypass
*   **Severity:** High
*   **File:** `server/src/mcp_server.py` (Line 30), `server/src/config.py` (Line 30)
*   **Description:** MCP `transport_security` disables SDK DNS rebinding protection in favor of custom Origin validation in `main.py`. However, `_allowed_origins` relies on `settings.get_cors_origins_list()`. If `CORS_ORIGINS` is misconfigured or defaults to a wide list, the protection is bypassed. Additionally, `main.py` (Line 435) allows requests without an Origin header ("server-to-server").
*   **Exploit Scenario:** An attacker can host a malicious webpage that makes cross-origin requests to the local MCP server on standard ports. By spoofing or omitting the Origin header (e.g., via non-browser tools or exploited local proxies), they bypass the validation and execute arbitrary MCP tools.
*   **Recommended Fix:** Re-enable `enable_dns_rebinding_protection=True` in the SDK if an FQDN is available. Enforce strict `Origin` and `Host` header checks for all incoming requests, rejecting connections that omit them unless explicitly authenticated via server-to-server API keys.

---

## 2. Data Isolation Audit

### Finding 4: Global Workspace Override Bleed (Context Bleed)
*   **Severity:** Medium
*   **File:** `server/src/mcp_server.py` (Line 66, 115)
*   **Description:** The MCP server uses a global dictionary `_workspace_override: dict[str, str]` keyed by `ctx.user_email` to persist the chosen active workspace across stateless tool calls. Because the key is the email address and not a session identifier, this state is shared globally across all clients for that user.
*   **Exploit Scenario:** If a user has two browser tabs open, or is using Claude Desktop alongside the web UI, and switches workspaces in one client, the active workspace will suddenly change in the other client, leading to actions or decisions being written into the wrong workspace database.
*   **Recommended Fix:** Key the `_workspace_override` dictionary by a combination of `user_email` and `session_id` (extracted from `mcp-session-id` or similar token unique to the client session), or require clients to explicitly pass the `x-workspace-id` header on every request.

### Finding 5: `get_db` Context Manager Ignores Request Context
*   **Severity:** Medium
*   **File:** `server/src/database.py` (Line 321)
*   **Description:** The `get_db()` context manager checks if `engine_registry` is available. If it is, it retrieves the engine using `settings.azure_sql_database`. This explicitly hardcodes the connection to the default legacy database, rather than using the active `WorkspaceContext.db_name` for the current request.
*   **Exploit Scenario:** Currently, `get_db()` is used for legacy client tokens and OAuth. However, if any new REST API endpoints or background tasks are added using `get_db()` instead of `_get_engine_for_ctx(ctx)`, they will mistakenly write or read data from the global legacy database instead of the isolated tenant database, causing a massive cross-tenant data leak.
*   **Recommended Fix:** Remove `get_db()` usage entirely for application data, replacing it strictly with `get_workspace_db` or explicitly passing the engine. If used for auth, rename it to `get_auth_db()` to make its scope explicitly clear and prevent accidental usage for workspace data operations.

### Finding 6: Legacy Missing Engine Fallback Context Bleed
*   **Severity:** Low
*   **File:** `server/src/mcp_server.py` (Line 92, 132)
*   **Description:** In `_mcp_tool_call()`, if `_db_module.engine_registry` is falsy (due to config error), the application routes all database traffic to `_get_engine()`, which connects to `settings.azure_sql_database`.
*   **Exploit Scenario:** If the engine registry fails to initialize or is disabled erroneously (but the app is still reachable), all users across all workspaces will have their write operations funneled into a single global database. While this is primarily an availability/failover misconfiguration, it results in cross-tenant data mixing.
*   **Recommended Fix:** If multi-tenant mode (`control_db_name`) is enabled but `engine_registry` is absent, the backend should fast-fail on database operations (`HTTP 500`) rather than silently mixing tenant data into the baseline database.


## 3. Error Handling Audit
*   **Finding:** Review complete. The backend implements a robust exponential backoff retry loop (`call_with_retry`) mapped to transient Azure SQL errors. Multi-step operations like `create_workspace` implement appropriate compensating actions (e.g., dropping orphaned databases) if subsequent steps fail. No dirty state vulnerabilities were identified.


## 4. Code Consistency

### Finding 7: Missing `offset` Implementation in SQL Layer
*   **Severity:** Low (Feature Gap)
*   **File:** `server/src/api.py`, `server/src/tools/meetings.py`, `server/src/tools/actions.py`, `server/src/tools/decisions.py`
*   **Description:** The REST API endpoints for listing entities (e.g. `list_meetings_endpoint`) explicitly define and accept an `offset` query parameter. However, this parameter is never passed to the underlying tool functions (e.g. `meetings.list_meetings`), and the underlying SQL queries only implement `TOP (limit)` without any `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` clause.
*   **Exploit Scenario:** A frontend client attempting to implement pagination beyond the first page of results will repeatedly receive the same first page, appearing as a broken feature.
*   **Recommended Fix:** Update the `list_*` functions in the `tools/` directory to accept `offset` as an argument, and refactor the SQL statements to use standard SQL Server pagination: `ORDER BY id DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY`.

### Finding 8: Deprecated `ClientToken` Logic Mixing
*   **Severity:** Low (Tech Debt)
*   **File:** `server/src/database.py`, `server/src/oauth.py`
*   **Description:** The codebase retains substantial legacy logic for `ClientToken` tables mapping back to the single-database era. Functions like `create_client_token` are marked "deprecated for workspace use", but `get_db()` actively points to the legacy engine to support OAuth token storage.
*   **Exploit Scenario:** Developers maintaining the backend might inadvertently use legacy token functions instead of control DB token functions, leading to fragmented auth states or relying on dead code paths in future refactors.
*   **Recommended Fix:** Isolate all legacy `ClientToken` functions into a dedicated `legacy_auth.py` file or similar, so they don't pollute the modern `database.py` connection manager file.


## 5. Test Coverage Gaps Audit

### Finding 9: Missing Core Logic Tests (CRUD Tools)
*   **Severity:** Medium
*   **File:** `server/tests/` (Missing files)
*   **Description:** The test suite covers permissions, workspace isolation, admin setup, and token hashing. However, there are no tests for the core business logic components: `tools/meetings.py`, `tools/actions.py`, and `tools/decisions.py`. 
*   **Exploit Scenario:** Without integration or unit tests for the actual SQL operations inside the tools, introducing features like pagination (see Finding 7) or modifying queries could introduce regressions or SQL injection vulnerabilities that go undetected by CI/CD.
*   **Recommended Fix:** Create integration tests (`test_tools_meetings.py`, etc.) that use a temporary test database to validate the CRUD operations, ensuring that actions link properly to meetings and that `check_permission` enforced inside the tools functions correctly against real database rows.

### Finding 10: Missing Token Strategy / Cache Tests
*   **Severity:** Medium
*   **File:** `server/tests/test_token_workspace.py`
*   **Description:** While `test_token_workspace.py` tests that tokens resolve to correct workspaces, there are no tests verifying the 5-minute TTL cache behavior in `main.py` (`_token_cache`).
*   **Exploit Scenario:** The lack of tests for the cache means that the revocation bypass (Finding 2) was not caught during development. Any future fixes to the cache could also regress without tests.
*   **Recommended Fix:** Add tests that explicitly mock the `time.time()` function to test TTL expiration, and verify that invalidating a token in the database successfully forces a cache miss on the next request.


## 6. Infrastructure & Deployment Review
*   **Finding:** Review complete. The Bicep templates (`infra/main.bicep`) correctly implement the Microsoft Cloud Adoption Framework (CAF) naming conventions while providing backward compatibility for legacy environments. The Dockerfile correctly defines a non-root `appuser` (UID 1000) and executes the application safely without hardcoded secrets. `CORSOrigins` are passed via environment variables dynamically. No infrastructure vulnerabilities identified.

---

### End of Code Review

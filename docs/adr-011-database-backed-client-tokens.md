## ADR-011: Database-Backed Per-Client API Keys

**Date:** 2026-02-09
**Status:** Accepted
**Deciders:** Agent (implementation), Caleb Lucas (review)

### Context
MCP authentication tokens were stored as a JSON mapping in the MCP_AUTH_TOKENS
environment variable. This required redeployment to add, remove, or rotate tokens.
No expiry, no revocation, no audit trail.

### Decision
Move token storage to a ClientToken database table. Store SHA256 hashes (not plaintext).
Support expiry dates, active/revoked status, and last-used tracking. Provide CLI script
for token lifecycle management. Add 5-minute in-memory cache to reduce DB load.

OAuth client registrations (for ChatGPT) are also persisted to an OAuthClient database
table and loaded into an in-memory cache on startup, surviving container restarts.

### Consequences
**Easier:** Token management without redeployment. Audit trail via LastUsedAt. Expiry support.
**Harder:** Database dependency for auth (mitigated by cache). 5-min revocation delay (acceptable).

### Alternatives Considered
| Option | Rejected Because |
|--------|------------------|
| Keep env var tokens | No rotation, revocation requires redeploy |
| Azure Key Vault for tokens | Can't query/list easily, no expiry logic |
| Full OAuth for all clients | Complexity overkill for MCP tool auth |
| Entra ID per-client apps | Requires client Azure AD, too complex for MVP |

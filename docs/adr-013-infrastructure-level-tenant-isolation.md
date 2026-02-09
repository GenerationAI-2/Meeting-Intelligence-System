## ADR-013: Infrastructure-Level Tenant Isolation

**Date:** 2026-02-09
**Status:** Accepted
**Deciders:** Agent (verification), Caleb Lucas (review)

### Context

Multi-tenancy can be achieved via row-level security (shared database) or infrastructure isolation (separate database per client). Given the per-client deployment model and small client count, we chose infrastructure isolation.

### Decision

Each client gets a separate resource group containing: Container App, SQL Server + Database, Key Vault, and managed identity. No shared data stores. Isolation verified with explicit negative test cases (see `docs/tenant-isolation-model.md` for full test results).

### Consequences

**Easier:** No RLS complexity. Complete data separation. Simple mental model. Each client can be independently scaled, upgraded, or decommissioned.

**Harder:** Higher per-client cost (~$20/month vs ~$5/month for RLS). More resources to manage. IaC required for consistent provisioning.

### Trigger to Revisit

- More than 20 clients (operational overhead of separate instances)
- Need for cross-client analytics or reporting
- Cost pressure requiring consolidation

### Alternatives Considered

| Option | Rejected Because |
|--------|------------------|
| Row-level security (shared DB) | Added complexity, harder to verify isolation, shared failure domain |
| Schema-per-tenant | Middle ground but still shares server resources and failure domain |
| Separate subscriptions | Overkill for current scale, billing complexity |

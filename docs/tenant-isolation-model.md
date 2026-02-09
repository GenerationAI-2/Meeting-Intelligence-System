# Tenant Isolation Model — Meeting Intelligence

## Architecture

Each client deployment is fully isolated at the infrastructure level:

```
Client A                              Client B
+---------------------+              +---------------------+
| Resource Group A     |              | Resource Group B     |
|                      |              |                      |
| Container App A      |              | Container App B      |
|   +- Identity A -----+--X----------+---X                  |
|                      |              |                      |
| SQL Database A <-----+              | SQL Database B <-----+
|                      |              |                      |
| Key Vault A          |              | Key Vault B          |
|                      |              |                      |
| ClientToken table    |              | ClientToken table    |
| (auth tokens for A)  |              | (auth tokens for B)  |
+---------------------+              +---------------------+
         |                                      |
         +------------ Shared -----------------+
                  Container Registry (read-only)
                  Azure Subscription
                  Azure AD Tenant
```

## What's Isolated

| Resource | Isolation Method |
|----------|-----------------|
| Compute | Separate Container App per client |
| Data | Separate SQL Server + Database per client |
| Auth tokens | Stored in client's own database (ClientToken table) |
| Secrets | Separate Key Vault per client |
| Identity | System-assigned managed identity per Container App |
| Environment config | Separate env vars (ALLOWED_USERS, CORS_ORIGINS, etc.) |
| Monitoring | Separate App Insights + Log Analytics per resource group |

## What's Shared

| Resource | Risk | Mitigation |
|----------|------|-----------|
| Container Registry | Read-only access, same image | No client data in images |
| Azure Subscription | Subscription-level access | RBAC scoped to resource groups |
| Azure AD Tenant | Shared identity provider | ALLOWED_USERS per instance |
| Network (no VNet) | Public SQL endpoint | Identity-level auth (managed identity), no shared credentials |

## Verified Test Results

All tests conducted on 2026-02-09 between the **team** instance (`meeting-intelligence-team` in `meeting-intelligence-team-rg`) and an **isolation-test** instance (`mi-isolation-test` in `meeting-intelligence-isolation-test-rg`) deployed via Bicep IaC.

| # | Test | Result | Details |
|---|------|--------|---------|
| 1 | Cross-DB access via managed identity | **BLOCKED** | Team MI (46b2caa7) has zero role assignments on isolation-test SQL server. Isolation-test MI (820bf38a) has zero role assignments on team resources. |
| 2 | Data visibility across instances | **NO CROSS-CONTAMINATION** | Entirely separate SQL servers: `genai-sql-server` (team) vs `mi-isolation-test-sql` (isolation-test). No shared database. |
| 3 | Cross-instance token auth (REST API) | **401 REJECTED** | Fake/foreign tokens return HTTP 401 on `/api/meetings`. Tokens are per-database; a token from one instance's DB does not exist in another's. |
| 4 | Cross-instance SSE connection | **401 REJECTED** | Fake/foreign tokens return HTTP 401 on `/sse?token=...`. |
| 5 | Cross-instance Streamable HTTP | **401 REJECTED** | Fake/foreign tokens return HTTP 401 on `/mcp/<token>`. |
| 6 | Key Vault cross-access | **NO ACCESS** | Team MI has zero role assignments on `mi-isolation-test-kv`. Isolation-test MI has zero role assignments on team Key Vault. |
| 7 | SQL firewall rules | **AZURE-SERVICES ONLY** | Isolation-test SQL: only `AllowAzureServices (0.0.0.0)`. Team SQL: Azure services + query editor IPs (Portal access, cosmetic). |

### IaC Validation

The isolation-test instance was deployed using `infra/deploy-bicep.sh isolation-test`, confirming that the Bicep IaC templates can stamp out new client environments. The deployment created:
- Resource group: `meeting-intelligence-isolation-test-rg`
- Container App: `mi-isolation-test` with system-assigned managed identity
- SQL Server: `mi-isolation-test-sql` with Azure AD-only auth
- SQL Database: `mi-isolation-test` (Basic tier, TDE enabled, auditing on)
- Key Vault: `mi-isolation-test-kv` with JWT secret and App Insights connection
- Log Analytics workspace and App Insights instance
- Budget alert ($50 AUD/month)

## Accepted Risks

1. **No VNet isolation** — SQL endpoints are technically public. Mitigated by managed identity auth (no passwords) and Azure SQL firewall (Azure services only). Direct SQL connection requires a valid Azure AD token scoped to the specific database.
   *Trigger to revisit:* Client compliance requirement, security audit finding.

2. **Shared subscription** — An Azure admin could access all resource groups.
   Mitigated by RBAC scoped to resource groups. *Trigger to revisit:* Multi-organisation deployment.

3. **Shared monitoring** — Application Insights receives telemetry from all instances (separate workspace per environment). Mitigated by filtering on resource group/instance name.
   *Trigger to revisit:* Client data appearing in logs (sanitise sensitive fields).

4. **Shared Container Registry** — All instances pull images from the same ACR. Images contain no client-specific data or secrets. ACR access is read-only (AcrPull role).
   *Trigger to revisit:* Per-client image customisation requirement.

## Future Hardening (LATER)

- Private endpoints for Azure SQL (~$8/month per endpoint)
- VNet integration for Container Apps
- Separate subscriptions per client (enterprise only)
- Dedicated App Insights workspace per client
- Network Security Groups for inter-service traffic

# DOC2 — Technical Architecture Brief

**Meeting Intelligence System**
**Version:** 1.0 — 27 February 2026
**Audience:** Craig Corfield / CorIT infrastructure team
**Owner:** Caleb Lucas, Generation AI

---

## What It Is

A meeting intelligence platform that captures meetings, actions, and decisions from team discussions. Clients interact via AI assistants (Claude, Copilot) using the MCP protocol, or through a React web UI. Built on Azure, deployed as a single container per client with full tenant isolation.

---

## Per-Client Resource Footprint

Each client environment is a self-contained resource group with no cross-client dependencies.

| Resource | Naming (CAF) | SKU / Config |
|----------|-------------|-------------|
| Resource Group | `rg-app-prod-mi-<client>` | — |
| Container App | `ca-mi-prod-<client>` | 0.25 vCPU, 0.5 GiB RAM, 1-10 replicas |
| Container App Environment | `cae-mi-prod-<client>` | Consumption plan |
| SQL Server | `sql-mi-prod-<client>` | Azure AD-only auth, TLS 1.2 minimum |
| SQL Database (workspace) | `sqldb-mi-prod-<client>` | Basic tier, 5 DTU, TDE enabled |
| SQL Database (control) | `sqldb-mi-prod-<client>-control` | Basic tier, 5 DTU, TDE enabled |
| Key Vault | `kv-mi-prod-<client>` | Standard, soft-delete 90d, purge protection |
| Log Analytics | `log-mi-prod-<client>` | PerGB2018, 30-day retention |
| Application Insights | `appi-mi-prod-<client>` | Linked to Log Analytics |
| Action Group | `ag-mi-prod-<client>` | Email alerts |
| Container Registry | `acr-mi-prod-<client>` | Basic tier, admin disabled, managed identity pull |

**Estimated cost:** ~$20-30 AUD/month per client environment (always-on, Basic SQL tier).

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│  Client Resource Group (rg-app-prod-mi-<client>)    │
│                                                     │
│  ┌──────────────┐     ┌───────────────────────┐    │
│  │ Key Vault    │────▶│ Container App          │    │
│  │ (AppInsights │     │ (Python/FastAPI)       │    │
│  │  conn string)│     │                        │    │
│  └──────────────┘     │  Port 8000 (internal)  │    │
│                       │  HTTPS 443 (ingress)   │    │
│                       │                        │    │
│                       │  Endpoints:            │    │
│                       │  /api/*    REST (web)  │    │
│                       │  /mcp      HTTP (MCP)  │    │
│                       └───────┬───────────────┘    │
│                               │ Managed Identity    │
│                               ▼                     │
│  ┌────────────────────────────────────────────┐    │
│  │ SQL Server (Azure AD-only auth)            │    │
│  │                                            │    │
│  │  ┌──────────────┐  ┌───────────────────┐  │    │
│  │  │ Control DB   │  │ Workspace DB(s)   │  │    │
│  │  │ - users      │  │ - Meeting         │  │    │
│  │  │ - workspaces │  │ - Action          │  │    │
│  │  │ - members    │  │ - Decision        │  │    │
│  │  │ - tokens     │  │                   │  │    │
│  │  │ - audit_log  │  │                   │  │    │
│  │  └──────────────┘  └───────────────────┘  │    │
│  └────────────────────────────────────────────┘    │
│                                                     │
│  ┌──────────────┐  ┌────────────────────────┐      │
│  │ Log Analytics │  │ Application Insights   │      │
│  │ + SQL Audit   │  │ + 7 Alert Rules        │      │
│  └──────────────┘  └────────────────────────┘      │
└─────────────────────────────────────────────────────┘

│  ┌──────────────────┐                                │
│  │ Container        │◀── AcrPull role (MI identity)  │
│  │ Registry (ACR)   │                                │
│  └──────────────────┘                                │
```

---

## Authentication & Identity

No shared passwords anywhere in the system. All service-to-service auth uses managed identity.

**Container App → SQL Server:** System-assigned managed identity. The MI principal is granted `db_datareader` + `db_datawriter` on both databases, plus `dbmanager` on master (for runtime workspace database creation via admin API).

**Container App → Key Vault:** System-assigned managed identity with Key Vault Secrets User RBAC role. Secrets mounted as environment variables at runtime.

**Container App → ACR:** System-assigned managed identity with AcrPull role.

**End Users → Web UI:** Azure AD OAuth 2.0 via MSAL. App Registration per client with SPA redirect URIs. Token version v2 required. Access controlled via workspace memberships in control DB.

**AI Tools → MCP API:** Personal Access Tokens (SHA256 hashed, stored in control DB). Self-service generation via web UI. 5-minute in-memory cache. Rate limited at 120 requests/min per token.

**SQL Server Firewall:** `AllowAllWindowsAzureIps` rule only — no public endpoint access. Managed identity required for all connections.

---

## Security Controls

| Control | Implementation |
|---------|---------------|
| Encryption at rest | TDE on all SQL databases, Key Vault soft-delete + purge protection |
| Encryption in transit | TLS 1.2 minimum on SQL, HTTPS-only on Container App ingress |
| Identity | Azure AD-only SQL auth, managed identity for all service connections |
| Network | No public SQL endpoint, CORS restricted per environment, Azure-services-only firewall |
| Container | Non-root user (`appuser` UID 1000), multi-stage build, no shell in production image |
| Secrets | Key Vault for telemetry credentials, no env vars with plaintext secrets |
| RBAC | 4-tier role model (viewer/member/chair/org_admin), audit logged |
| Input validation | Pydantic schemas on all API/MCP inputs, HTML stripping, null byte filtering |
| Rate limiting | Tiered: MCP 120/min per token, API 60/min per IP |
| Audit | All data operations logged to `audit_log` table + SQL Server audit to Log Analytics |
| Headers | X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy, Permissions-Policy |

---

## Monitoring & Alerting

7 alert rules deployed via Bicep per environment, all email to `caleb.lucas@generationai.co.nz`:

| Alert | Trigger | Severity |
|-------|---------|----------|
| 5xx errors | >5 in 5 min | Critical |
| Replica down | 0 replicas (always-on only) | Critical |
| Auth failure spike | >20 × 401 in 5 min | Critical |
| Response time | Avg >5s over 5 min | Warning |
| Container restarts | >3 in 5 min | Warning |
| CPU | >90% | Warning |
| Memory | >90% | Warning |

SQL diagnostic settings stream 11 log categories (including `SQLSecurityAuditEvents`) + 3 metric categories to Log Analytics with 90-day retention.

---

## Recovery Targets

| Scenario | RPO | RTO |
|----------|-----|-----|
| Bad deployment | 0 | 5 min (revision rollback) |
| Database corruption | 15 min | 30 min (PITR to new DB + swap) |
| Full environment rebuild | 15 min | 60 min (Bicep IaC from scratch + PITR) |
| Regional outage | 1 hour | 4 hours (manual alternate-region deploy) |

Azure SQL Basic tier: 7-day PITR retention, automatic daily backups. Tested: restore completes in <5 minutes at current data volumes.

All infrastructure is codified in Bicep — a full environment can be rebuilt from scratch in ~60 minutes with no manual Azure Portal steps.

---

## Deployment Model

**Provisioning flow:**

1. Craig's team provisions Azure subscription with management groups + RBAC
2. We create App Registration in the client's Azure AD tenant
3. We create a `.bicepparam` file with client-specific config
4. `deploy-new-client.sh` runs: Bicep infra → SQL setup → token generation → health check
5. Craig's team runs security standup in parallel (Sentinel, SOC, ITSM — ~7 days)
6. Client receives web UI URL + MCP connection instructions

**Image management:** Per-client ACR, timestamp-tagged images (`mi-<env>:20260227120000`). Rollback by activating a previous Container App revision (<5 min).

**What Craig's team needs to provide per client:**
- Subscription with appropriate management groups
- Network connectivity (if VNet integration required — not default)
- Global Admin consent for the App Registration (one-time)

**What we manage:**
- Container image builds and deployments
- Database schema and migrations
- User provisioning and token management
- Monitoring and incident response

---

## Upgrade Path

| Enhancement | Trigger | Additional Cost |
|-------------|---------|----------------|
| SQL Standard tier (longer retention, geo-replication) | Enterprise RPO requirement | ~$20/month |
| VNet integration + private endpoints | Enterprise network policy | ~$8/month per endpoint |
| Microsoft Defender for Containers | 10+ clients | $7/month per cluster |
| Multi-region deployment | Regional failover requirement | ~$60/month (duplicate resources) |
| Custom domain + TLS | Client branding | DNS + managed certificate (free via Container Apps) |

---

*This brief covers the technical architecture as deployed. For deployment procedures, see `DOC3-client-deploy-runbook.md`. For operational procedures, see `DOC4-breakglass-ops-runbook.md`.*

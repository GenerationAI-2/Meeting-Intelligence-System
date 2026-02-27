# DOC3 — Client Deploy Runbook

**Meeting Intelligence System**
**Version:** 1.0 — 27 February 2026
**Owner:** Caleb Lucas

End-to-end checklist for deploying a new client environment. Estimated time: 30-45 minutes (plus 7-10 days for Craig's security standup running in parallel).

---

## Prerequisites

Before starting, confirm you have:

- [ ] Azure CLI authenticated (`az login`)
- [ ] `sqlcmd` installed (`brew install sqlcmd`)
- [ ] `uv` installed (Python package manager)
- [ ] ODBC Driver 18 for SQL Server installed
- [ ] `.env.deploy` file present (for any environment-specific secrets)
- [ ] Client name decided (max 10 chars, lowercase, e.g. `acme-corp`)
- [ ] App Registration created in Azure AD (Client ID noted)
- [ ] Client email addresses for web UI access
- [ ] Craig's team has provisioned the subscription with management groups + RBAC

---

## Step 1: Create Parameter File

Copy the CAF naming template and fill in client details:

```bash
cp infra/parameters/_template-caf.bicepparam infra/parameters/<client-name>.bicepparam
```

Edit the new file — replace all `<PLACEHOLDER>` values:

| Parameter | Example | Notes |
|-----------|---------|-------|
| `environmentName` | `acme-corp` | Max 10 chars for Key Vault compatibility |
| `environmentType` | `prod` | Always `prod` for clients |
| `sqlAdminObjectId` | Azure AD Object ID | For SQL admin access |
| `sqlAdminDisplayName` | `Caleb Lucas` | |
| `azureTenantId` | `12e7fcaa-...` | Client's Azure AD tenant |
| `azureClientId` | App Registration Client ID | Created in prereqs |
| `allowedUsers` | `john@acme.com,jane@acme.com` | Comma-separated |
| `corsOrigins` | `https://placeholder` | Auto-updated in Phase 4 |
| `minReplicas` | `1` | Always 1 for client-facing |

**Gotcha:** Key Vault names have a 24-char limit. The generated name is `kv-mi-prod-<client>` — if client name exceeds 10 chars, the deploy will fail.

---

## Step 2: Run the Deploy Script

The script handles everything in sequence: App Registration config → Bicep infra → SQL setup → token generation → CORS writeback → health check.

```bash
./infra/deploy-new-client.sh <client-name>
```

Optionally specify an image tag (defaults to current timestamp):

```bash
./infra/deploy-new-client.sh <client-name> 20260227120000
```

The script runs 6 phases:

| Phase | What it does | Automated? |
|-------|-------------|------------|
| 0 | App Registration — identifier URI, OAuth scope, token v2 | Yes |
| 1 | Bicep infrastructure — Container App, SQL, Key Vault, monitoring | Yes |
| Firewall | Temporary SQL firewall rule for deployer IP (auto-removed on exit) | Yes |
| 2 | Database init — MI user, control schema, workspace schema, migrations, seed | Yes |
| 3 | Token generation — first user + workspace membership + MCP token | Yes |
| 4 | CORS origin writeback to param file | Yes |
| 5 | Final health check | Yes |

**Expected output:** A deployment summary with status for each phase and the environment URLs.

---

## Step 3: Manual Steps

Three things the script cannot automate:

### 3a. API Consent

For the Generation AI subscription, user consent has been sufficient — each user approves the app permissions on first login. For other client tenants, this may require admin consent depending on their Azure AD policies:

```
Azure Portal → App Registrations → <Client ID> → API Permissions → Grant admin consent
```

Check the client's tenant consent settings. If user consent is disabled tenant-wide, a Global Admin will need to grant consent or the web UI login will fail with a permissions error.

### 3b. Commit the Parameter File

The CORS origin gets written back to the param file. Commit it:

```bash
git add infra/parameters/<client-name>.bicepparam
git commit -m "chore: add parameter file for <client-name>"
git push origin main
```

### 3c. Verify CONTROL_DB_NAME is Set

The Bicep template sets `CONTROL_DB_NAME` automatically. Verify it's present:

```bash
az containerapp show -n mi-<client-name> -g meeting-intelligence-<client-name>-rg \
  --query "properties.template.containers[0].env[?name=='CONTROL_DB_NAME'].value" -o tsv
```

If empty (shouldn't happen on new deploys), set it manually:

```bash
az containerapp update -n mi-<client-name> -g meeting-intelligence-<client-name>-rg \
  --set-env-vars CONTROL_DB_NAME=mi-<client-name>-control
```

**Gotcha:** Without this, the app falls back to legacy mode which grants full admin to all users.

---

## Step 4: Verify

Run these checks before handing anything to the client:

```bash
# Health
curl -sf https://<FQDN>/health/ready | jq
# Expected: {"status": "ready", "database": "connected"}

# MCP auth (with the token generated in Phase 3)
curl -sf "https://<FQDN>/mcp" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
# Expected: JSON response with server capabilities

# Web UI
# Open https://<FQDN> in browser, log in with Azure AD, verify Settings page loads
```

---

## Step 5: Client Configuration

Provide the client with connection details for their AI tools. The Settings page in the web UI shows dynamic connection URLs per instance.

### Claude.ai (Custom Connector)

Add as a custom connector with this URL:

```
https://<FQDN>/mcp?token=<TOKEN>
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "meeting-intelligence": {
      "url": "https://<FQDN>/mcp",
      "headers": {
        "Authorization": "Bearer <TOKEN>"
      }
    }
  }
}
```

### Other MCP Clients (Copilot, etc.)

```
MCP Server URL: https://<FQDN>/mcp
Auth: Bearer token in Authorization header, or X-API-Key header
```

### Web UI

```
URL: https://<FQDN>
Auth: Azure AD login (users must be workspace members in control DB)
```

---

## Rollback

If the deployment is broken and can't be fixed quickly:

```bash
# 1. List revisions
az containerapp revision list -n mi-<env> -g meeting-intelligence-<env>-rg -o table

# 2. Activate the previous working revision
az containerapp revision activate -n mi-<env> -g <rg> --revision <previous-revision>

# 3. Route all traffic to it
az containerapp ingress traffic set -n mi-<env> -g <rg> --revision-weight <previous-revision>=100

# 4. Verify
curl -sf https://<FQDN>/health/ready
```

For a full environment teardown (if needed):

```bash
az group delete -n meeting-intelligence-<env>-rg --yes --no-wait
```

---

## Craig's Parallel Security Standup

While you run the technical deployment, Craig's team runs their security standup in parallel (~7 days):

- Sentinel (SIEM) learning period
- SOC connector
- ITSM tooling
- Management groups + RBAC at subscription level

Tell clients **2 weeks** total lead time. Our Bicep deployment runs in the first day; Craig's security controls fill the rest.

---

---

## Known Gotchas

Documented failures from battle-testing and real deployments. Internal reference — don't share with clients.

| Issue | Symptom | Fix |
|-------|---------|-----|
| Key Vault RBAC propagation | Container crash-loops with `secret not found` | Wait 5-10 min after first deploy, then force a new revision: `az containerapp update -n mi-<env> -g <rg> --set-env-vars FORCE_RESTART=$(date +%s)` |
| AcrPull role not assigned | Image pull failure on first deploy | `az role assignment create --assignee <MI-principal-id> --role AcrPull --scope <ACR-resource-id>` |
| SPA redirect URI mismatch | AADSTS50011 error on web UI login | Register BOTH `https://<FQDN>` AND `https://<FQDN>/auth/callback` as SPA redirect URIs |
| Token version v1 vs v2 | 401 "Invalid issuer" on web UI login | Phase 0 should handle this. If not: App Registration manifest → set `accessTokenAcceptedVersion` to `2` |
| Container readiness probe caches | Health probe passes but app returns 500 | Restart the revision: `az containerapp revision restart -n <app> -g <rg> --revision <rev>` |
| Provisioning lock after killed CLI | All `az containerapp` commands fail for ~30 min | Wait. Azure releases the lock automatically. |
| Email mismatch | User gets full admin access (RBAC bypass) | Verify Azure AD emails match exactly what's seeded in control DB |
| Missing VITE build args | Web UI shows placeholder tenant IDs | Rebuild image with all `--build-arg VITE_*` flags (see CLAUDE.md) |

---

*Keep this runbook updated when deploy scripts change. Last validated against `deploy-new-client.sh` at commit `a4d2f0e`.*

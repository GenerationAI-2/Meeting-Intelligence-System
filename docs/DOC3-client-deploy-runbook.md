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

### 3a. Admin Consent (MANDATORY for client apps)

**All client apps require admin consent.** Client users are B2B guests in the MyAdvisor tenant — guests cannot self-consent under the tenant's `microsoft-user-default-recommended` consent policy. Without admin consent, guest users hit a misleading "does not exist in tenant" error at Azure AD login.

A Global Administrator (Mark) must grant consent:

```
Azure Portal → Enterprise Applications → mi-<client>-prod → Permissions → Grant admin consent for MyAdvisor
```

Or via direct URL (send to Mark):
```
https://login.microsoftonline.com/12e7fcaa-f776-4545-aacf-e89be7737cf3/adminconsent?client_id=<CLIENT_ID>
```

**Verify consent was granted:**
```bash
SP_ID=$(az rest --method GET --url "https://graph.microsoft.com/v1.0/servicePrincipals?\$filter=appId eq '<CLIENT_ID>'" --query "value[0].id" -o tsv)
az rest --method GET --url "https://graph.microsoft.com/v1.0/servicePrincipals/${SP_ID}/oauth2PermissionGrants" -o json
# Should return at least one grant with consentType: "AllPrincipals"
```

**Why this is mandatory:** All client deployments use the MyAdvisor tenant (`12e7fcaa-...`). Client users (e.g., `@fero.co.nz`, `@victoryknives.co.nz`) are B2B guests. Guests can authenticate (B2B invitation handles that) but cannot consent to app permissions. Admin consent bridges this gap.

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
az containerapp show -n ca-mi-prod-<client-name> -g rg-app-prod-mi-<client-name> \
  --query "properties.template.containers[0].env[?name=='CONTROL_DB_NAME'].value" -o tsv
```

If empty (shouldn't happen on new deploys), set it manually:

```bash
az containerapp update -n ca-mi-prod-<client-name> -g rg-app-prod-mi-<client-name> \
  --set-env-vars CONTROL_DB_NAME=sqldb-mi-prod-<client-name>-control
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

Send the client their Quick Start Guide (DOC1) with the instance URL. They self-service from there:

1. Sign in to the web UI at `https://<FQDN>`
2. Go to Settings → Create Token (self-service, one-time)
3. Connect via Claude.ai custom connector using: `https://<FQDN>/mcp?token=<TOKEN>`

The deploy script (Phase 3) creates the first admin user and token automatically. Additional users generate their own tokens via the web UI.

---

## Rollback

If the deployment is broken and can't be fixed quickly:

```bash
# 1. List revisions
az containerapp revision list -n ca-mi-prod-<env> -g rg-app-prod-mi-<env> -o table

# 2. Activate the previous working revision
az containerapp revision activate -n ca-mi-prod-<env> -g rg-app-prod-mi-<env> --revision <previous-revision>

# 3. Route all traffic to it
az containerapp ingress traffic set -n ca-mi-prod-<env> -g rg-app-prod-mi-<env> --revision-weight <previous-revision>=100

# 4. Verify
curl -sf https://<FQDN>/health/ready
```

For a full environment teardown (if needed):

```bash
az group delete -n rg-app-prod-mi-<env> --yes --no-wait
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

*Keep this runbook updated when deploy scripts change. Last validated against `deploy-new-client.sh` at commit `332852f`.*

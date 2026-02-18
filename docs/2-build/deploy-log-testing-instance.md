# Deployment Log: testing-instance

**Date:** 2026-02-19
**Deployer:** Claude Code (Opus 4.6) + Caleb Lucas
**Image Tag:** 20260219055339
**Status:** COMPLETE

---

## Environment Details

| Field | Value |
|-------|-------|
| Environment Name | testing-instance |
| Resource Group | meeting-intelligence-testing-instance-rg |
| Container App | mi-testing-instance |
| FQDN | mi-testing-instance.icycliff-e324f345.australiaeast.azurecontainerapps.io |
| URL | https://mi-testing-instance.icycliff-e324f345.australiaeast.azurecontainerapps.io |
| SQL Server | mi-testing-instance-sql.database.windows.net |
| SQL Database | mi-testing-instance |
| Key Vault | mi-testing-instance-kv |
| App Registration | 291556f7-8e73-4b80-8a20-68dfa999a55c (single reg for SPA + API) |
| Tenant ID | 12e7fcaa-f776-4545-aacf-e89be7737cf3 |
| Region | australiaeast |
| Min Replicas | 1 |
| Allowed Users | caleb.lucas@generationai.co.nz, mark.lucas@generationai.co.nz |

---

## Errors Encountered and Resolutions

### 1. Admin Consent Requires Global Admin

**Phase:** 2 (App Registration)
**Symptom:** `az ad app permission admin-consent` returned `Authorization_RequestDenied` — "This operation can only be performed by an administrator."
**Root Cause:** The deploying user (caleb.lucas) is not a Global Administrator in the Azure AD tenant. Admin consent for API permissions requires GA or Privileged Role Admin.
**Resolution:** Skipped admin consent. Individual users will be prompted for consent on first login. A tenant admin can grant org-wide consent later via Azure Portal > App Registrations > API Permissions > Grant admin consent.
**Impact:** Low — first login per user will show a consent prompt. No functionality impact.
**Automation Gap:** `deploy-new-client.sh` should document this as a manual step or detect the error and continue.

### 2. AcrPull Role Not Assigned by Bicep

**Phase:** 4 (First Bicep Deploy)
**Symptom:** Container App module stuck in "Running/InProgress" for 17+ minutes. No revision created. System logs only showed event collector connection — no image pull attempts.
**Root Cause:** Bicep `container-app.bicep` uses `identity: 'system'` for ACR registry config, but this does NOT create an AcrPull role assignment on the container registry. The Container App cannot pull images without this role.
**Resolution:** Manually assigned AcrPull role:
```bash
PRINCIPAL_ID=$(az containerapp show -n mi-testing-instance -g meeting-intelligence-testing-instance-rg --query "identity.principalId" -o tsv)
ACR_ID=$(az acr show --name meetingintelacr20260116 --query id -o tsv)
az role assignment create --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID"
```
**Impact:** Critical — deployment cannot succeed without this. This is the same issue documented in CLAUDE.md "What's Been Tried & Failed" for the marshall deploy.
**Automation Gap:** `deploy-bicep.sh` should assign AcrPull automatically after the Container App is created, or Bicep should include a role assignment module for ACR.

### 3. Bicep Deployment Doesn't Self-Recover After Mid-Deploy Fix

**Phase:** 4 (First Bicep Deploy)
**Symptom:** After assigning AcrPull mid-deployment, the containerapp module stayed stuck and eventually timed out.
**Root Cause:** Azure doesn't retry the image pull just because permissions changed during a running ARM deployment. The ARM operation waits for the original revision creation to complete, which never starts the pull.
**Resolution:** Must let the deployment fail/cancel, then re-run `deploy-bicep.sh` with the same image tag.
**Impact:** Wasted ~22 minutes waiting for the first deploy to timeout.
**Automation Gap:** `deploy-new-client.sh` should assign AcrPull BEFORE the Bicep deploy, not after. The recommended sequence is:
1. Create resource group
2. Run a minimal Bicep deploy (just Container App to get the managed identity)
3. Assign AcrPull
4. Run full Bicep deploy

### 4. `az containerapp update --image` Creates Broken Revision on Failed First Deploy

**Phase:** 4 (Recovery attempt)
**Symptom:** Tried `az containerapp update --image` to force a new revision after the first deploy failed. Image pulled successfully but container immediately crashed with: `Error: secret "capp-mi-testing-instance" not found`
**Root Cause:** The original Bicep deployment never completed the containerapp module, so the Kubernetes-level secret object for Key Vault references (JWT_SECRET, APPLICATIONINSIGHTS_CONNECTION_STRING) was never created. `az containerapp update --image` only updates the image — it doesn't recreate the secret infrastructure.
**Resolution:** Don't use `az containerapp update` to work around a failed first deploy. Re-run the full Bicep deployment instead.
**Impact:** The update operation also locked the Container App in "InProgress" provisioning state for ~30 minutes, blocking all subsequent modifications.
**Automation Gap:** Document this as a "don't do" in the deployment guide. If the first deploy fails at containerapp, the only correct recovery is re-running the full Bicep deploy.

### 5. Container App Provisioning Lock After Killed CLI

**Phase:** 4 (Recovery attempt)
**Symptom:** After killing the `az containerapp update` CLI process, the Container App stayed in "InProgress" provisioning state for 30+ minutes, blocking all Bicep re-deploys with `ContainerAppOperationInProgress`.
**Root Cause:** Killing the local CLI process does NOT cancel the Azure-side ARM operation. The operation continues independently and must timeout on its own (~30 min).
**Resolution:** Wait for the operation to timeout. There is no CLI command to cancel an in-flight Container App provisioning operation.
**Impact:** ~30 minutes of dead time waiting for the lock to clear.
**Automation Gap:** `deploy-new-client.sh` should never attempt `az containerapp update` during initial setup. Only use it for image-only updates on already-working environments.

### 6. Failure-Anomalies-Alert-Rule Deployment Failed

**Phase:** 4 (First Bicep Deploy)
**Symptom:** A deployment named `Failure-Anomalies-Alert-Rule-Deployment-*` showed as Failed.
**Root Cause:** Auto-created by Application Insights smart detection. Not controlled by our Bicep templates.
**Resolution:** Ignored — benign.
**Impact:** None.

### 7. Identity and Alerts Modules Never Ran

**Phase:** 4 (First Bicep Deploy)
**Symptom:** After the first Bicep deploy was cancelled, only monitoring, keyvault, and sql modules had succeeded. The identity and alerts modules never ran.
**Root Cause:** Both depend on outputs from the containerapp module (principalId, containerAppId). Since containerapp never completed, these modules were never started.
**Resolution:** They will run on the next successful Bicep deploy.
**Impact:** Container App had no Key Vault Secrets User role (couldn't read JWT_SECRET), and no alert rules were created.

### 8. K8s Secret Not Created Due to Key Vault RBAC Propagation Delay

**Phase:** 4 (Third Bicep Deploy — nominally successful)
**Symptom:** Bicep deploy succeeded (all modules completed), but Container App revision crash-looped with: `Error: secret "capp-mi-testing-instance" not found`. Health endpoints timed out.
**Root Cause:** The Bicep identity module assigns Key Vault Secrets User role to the Container App's managed identity. Azure Container Apps resolves Key Vault secret references into a Kubernetes secret object (`capp-<app-name>`). If RBAC hasn't propagated when the revision first starts, the K8s secret is never created — and Azure does NOT retry.
**Resolution:** Wait for RBAC to propagate (~5-10 min), then force a new revision:
```bash
az containerapp update -n mi-testing-instance -g meeting-intelligence-testing-instance-rg \
  --set-env-vars "RESTART_TRIGGER=force-$(date +%s)"
```
**Impact:** ~10 minutes of additional troubleshooting + one extra revision needed.
**Automation Gap:** `deploy-new-client.sh` should add a sleep (60-120s) between the Bicep deploy completing and any health checks. Or: split the deploy so identity module runs first, then containerapp module runs after a delay.

### 9. Alerts Module Failed — KQL Table Doesn't Exist Yet

**Phase:** 4 (Third Bicep Deploy)
**Symptom:** Alerts module failed deployment. All other 5 modules succeeded.
**Root Cause:** Alert rules use KQL queries against `ContainerAppConsoleLogs_CL` table, which doesn't exist in Log Analytics until the Container App has been running and emitting logs for some time.
**Resolution:** Ignored — benign. Alert rules can be deployed later via standalone Bicep deploy once the table exists.
**Impact:** No alert rules active initially. Will auto-resolve on next full Bicep deploy after app has run.

### 10. SPA Redirect URI Mismatch on Web UI Login

**Phase:** 8 (Verification)
**Symptom:** Azure AD login returned `AADSTS50011: The redirect URI 'https://mi-testing-instance.icycliff-e324f345.australiaeast.azurecontainerapps.io' specified in the request does not match the redirect URIs configured for the application`.
**Root Cause:** The web app's MSAL config (`web/src/authConfig.js`) uses `window.location.origin` as the redirect URI — which is the base URL with no path. But we only registered `https://<fqdn>/auth/callback`. Azure AD requires an exact match.
**Resolution:** Added the base URL (no path) to the SPA redirect URIs:
```bash
az ad app update --id 291556f7-8e73-4b80-8a20-68dfa999a55c \
  --set spa='{"redirectUris":["https://<fqdn>","https://<fqdn>/auth/callback","http://localhost:5173","http://localhost:5173/auth/callback"]}'
```
**Impact:** Web UI login blocked until fixed. Quick fix once identified.
**Automation Gap:** `deploy-new-client.sh` must register BOTH the base URL and `/auth/callback` as redirect URIs. Also register `localhost` variants for local dev.

---

## Manual Steps That Should Be Automated

| Step | What Was Done Manually | What `deploy-new-client.sh` Should Do |
|------|----------------------|---------------------------------------|
| AcrPull role assignment | `az role assignment create` after Container App created | Assign automatically — either pre-deploy (create CA first, then assign, then full deploy) or as a post-deploy step in the script |
| App Registration setup | `az ad app update` for token version, scopes, permissions, SPA redirect URIs | Script should accept app reg client ID and configure all of this |
| Admin consent | Failed — requires Global Admin | Detect the error, log it as a manual step, continue |
| Database schema | Run `schema.sql` manually via Azure Portal | Script should use `sqlcmd` with AAD auth to run schema + migrations |
| Database migrations | Run `002_client_tokens.sql` and `003_refresh_token_usage.sql` manually | Same — `sqlcmd` or invoke `migrate.py` with the new environment |
| Managed identity DB user | `CREATE USER [mi-testing-instance] FROM EXTERNAL PROVIDER` | Script should do this via `sqlcmd` after deploy |
| Token creation | Generate token locally, INSERT via Portal | Script should invoke `manage_tokens.py` or generate + insert directly |
| CORS origin update | Edit `.bicepparam`, re-deploy | Script should capture FQDN from first deploy and update param file automatically |
| SPA redirect URIs | `az ad app update --set spa='{...}'` with FQDN | Script should do this after capturing FQDN |
| Key Vault admin for deployer | `az role assignment create` for deployer user as Key Vault Administrator | Script should assign deployer user KV Admin for troubleshooting; or at minimum Key Vault Secrets Officer |
| Force new revision after RBAC | `az containerapp update --set-env-vars RESTART_TRIGGER=...` | Script should sleep 60-120s after Bicep deploy, then force a revision update to ensure K8s secret is created |

---

## Runbook Assumptions That Were Wrong

*Note: No runbook existed at `2-build/deploy-runbook-testing-instance.md` — the file was referenced in the brief but didn't exist. The `docs/deploy-marshall.md` brief was used as reference instead.*

| Assumption in Marshall Brief | Reality for testing-instance |
|------------------------------|------------------------------|
| "Build and push first" with `az acr build --image mi-marshall:$(git rev-parse --short HEAD)` | Image name must match Bicep pattern: `mi-${environmentName}:${tag}`. For testing-instance: `mi-testing-instance:$IMAGE_TAG` |
| ACR Pull role "may handle pulls automatically" | Never automatic. Always required. CLAUDE.md already documents this but the brief hedges. |
| `az ad app update --web-redirect-uris` | Must use `--set spa='{"redirectUris":[...]}'` for SPA platform (CLAUDE.md documents this correctly) |
| Run `deploy-bicep.sh` once, then fix up | Need at least 2 Bicep deploys: first creates resources (fails at containerapp), second completes after AcrPull is assigned |
| Managed identity user creation "may need to wait 2-5 minutes" | DB user must also be created before the Bicep deploy succeeds, not just before health checks pass. The app crash-loops without DB access, which prevents the revision from becoming ready, which blocks the Bicep deploy. |
| Bicep deploy "succeeds" = everything working | A successful Bicep deploy does NOT mean the app is healthy. Key Vault RBAC propagation can take 5-10 min. The K8s secret `capp-<app-name>` won't be created if RBAC hasn't propagated when the revision first starts. Need to force a new revision after a delay. |

---

## Suggestions for `deploy-new-client.sh`

### Recommended Deploy Sequence

```bash
#!/bin/bash
# deploy-new-client.sh <environment-name> <client-id> <image-tag>

ENV=$1
CLIENT_ID=$2
IMAGE_TAG=${3:-$(date +%Y%m%d%H%M%S)}
RG="meeting-intelligence-${ENV}-rg"

# Phase 1: Build image
az acr build --registry meetingintelacr20260116 \
  --image "mi-${ENV}:${IMAGE_TAG}" \
  --file server/Dockerfile \
  --build-arg VITE_SPA_CLIENT_ID=$CLIENT_ID \
  --build-arg VITE_API_CLIENT_ID=$CLIENT_ID \
  --build-arg VITE_AZURE_TENANT_ID=12e7fcaa-... \
  --build-arg VITE_API_URL=/api .

# Phase 2: Configure App Registration
az ad app update --id $CLIENT_ID \
  --set api='{"requestedAccessTokenVersion": 2}'
az ad app update --id $CLIENT_ID \
  --identifier-uris "api://$CLIENT_ID"
# ... expose scope, add User.Read, attempt admin consent (tolerate failure)

# Phase 3: First Bicep deploy (will fail at containerapp — that's expected)
export JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
export CONTAINER_IMAGE_TAG=$IMAGE_TAG
export APPLICATIONINSIGHTS_CONNECTION_STRING=""
./infra/deploy-bicep.sh $ENV $IMAGE_TAG || true  # Tolerate failure

# Phase 4: Assign AcrPull
PRINCIPAL_ID=$(az containerapp show -n mi-$ENV -g $RG --query identity.principalId -o tsv)
ACR_ID=$(az acr show --name meetingintelacr20260116 --query id -o tsv)
az role assignment create --assignee $PRINCIPAL_ID --role AcrPull --scope $ACR_ID

# Phase 5: Database setup (requires sqlcmd with AAD auth)
# sqlcmd -S mi-${ENV}-sql.database.windows.net -d mi-${ENV} -G --authentication-method=ActiveDirectoryDefault \
#   -i schema.sql -i server/migrations/002_client_tokens.sql -i server/migrations/003_refresh_token_usage.sql
# ... CREATE USER, token generation

# Phase 6: Update CORS with actual FQDN
FQDN=$(az containerapp show -n mi-$ENV -g $RG --query properties.configuration.ingress.fqdn -o tsv)
sed -i "s/REPLACE_AFTER_FIRST_DEPLOY_WITH_FQDN/https:\/\/$FQDN/" infra/parameters/${ENV}.bicepparam

# Phase 7: Set SPA redirect URIs
az ad app update --id $CLIENT_ID \
  --set spa="{\"redirectUris\":[\"https://$FQDN/auth/callback\",\"http://localhost:5173/auth/callback\"]}"

# Phase 8: Clean Bicep re-deploy
./infra/deploy-bicep.sh $ENV $IMAGE_TAG

# Phase 9: Verify
curl -sf "https://$FQDN/health/ready" && echo "READY" || echo "NOT READY"
```

### Key Design Principles

1. **Tolerate first-deploy failure** — The first Bicep deploy will always fail at containerapp because AcrPull isn't assigned yet. Accept this and move on.
2. **Assign AcrPull before second deploy** — Not after, not during.
3. **Database setup between deploys** — Schema, migrations, and MI user must exist before the second deploy so the app can start and readiness probe passes.
4. **Two-deploy pattern** — First creates resources and gets the managed identity. Second completes with everything wired up.
5. **CORS update is automatic** — Capture FQDN from first deploy, sed the param file, redeploy.

---

## Deployment Steps Completed

- [x] Phase 1: Prerequisites (Azure CLI verified, JWT secret generated)
- [x] Phase 2: App Registration configured (token v2, API scope, Graph permissions)
- [ ] Phase 2b: Admin consent (requires Global Admin — deferred)
- [x] Phase 3: Container image built and pushed (`mi-testing-instance:20260219055339`)
- [x] Phase 4a: First Bicep deploy (monitoring, keyvault, sql succeeded; containerapp failed)
- [x] Phase 4b: AcrPull role assigned
- [x] Phase 4c: Clean Bicep re-deploy (3rd attempt — all modules except alerts succeeded)
- [x] Phase 4d: Force new revision to pick up Key Vault secrets after RBAC propagation
- [x] Phase 5a: CORS origin updated in parameter file
- [x] Phase 5b: SPA redirect URIs set on App Registration
- [x] Phase 6: Database setup (schema, migrations, MI user, token — via Azure Portal Query Editor)
- [x] Phase 7: Auth token inserted
- [x] Phase 8: Health checks passing (`/health/live`, `/health/ready`, `/health`)
- [x] Phase 9: MCP endpoints verified (Streamable HTTP, SSE, path-based)
- [x] Phase 10: Web UI returns 200 (Azure AD login requires browser test)

---

## Client Configuration

### Claude Desktop (claude_desktop_config.json)
```json
{
  "mcpServers": {
    "meeting-intelligence": {
      "url": "https://mi-testing-instance.icycliff-e324f345.australiaeast.azurecontainerapps.io/sse?token=<PLAINTEXT_TOKEN>"
    }
  }
}
```

### Copilot Studio
```
Endpoint URL: https://mi-testing-instance.icycliff-e324f345.australiaeast.azurecontainerapps.io/mcp/<PLAINTEXT_TOKEN>
Transport: Streamable HTTP
```

### Web UI
```
URL: https://mi-testing-instance.icycliff-e324f345.australiaeast.azurecontainerapps.io
Login: Azure AD (caleb.lucas@generationai.co.nz or mark.lucas@generationai.co.nz)
```

---

## Rollback

```bash
az group delete --name meeting-intelligence-testing-instance-rg --yes --no-wait
# Also purge Key Vault (has purge protection):
az keyvault purge --name mi-testing-instance-kv
```

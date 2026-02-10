# Agent Brief: Deploy John Marshall's Production Environment

## Context

You are deploying a new production client environment for the Meeting Intelligence System. This is a **real client environment** — John Marshall (john.marshall@myadvisor.co.nz) is the first paying client.

The Meeting Intelligence System is a FastAPI + React application that provides meeting transcript management, action tracking, and decision logging via MCP (Model Context Protocol) for AI assistants (Claude, Copilot, ChatGPT) and a web UI.

Infrastructure is deployed using modular Bicep templates via `deploy-bicep.sh`. The IaC was validated during tenant isolation testing (Stream F) which successfully deployed and tore down a test environment.

## Client Details

- **Name:** John Marshall
- **Email:** john.marshall@myadvisor.co.nz
- **Environment Name:** `marshall`
- **Resource Group:** `meeting-intelligence-marshall-rg`
- **Container App Name:** `mi-marshall` (Bicep uses `mi-${environmentName}`)
- **Platforms:** Claude Desktop (SSE), Copilot (Streamable HTTP), ChatGPT (OAuth 2.1 PKCE)
- **Web UI:** Yes
- **Cold Start:** `minReplicas=1` (always warm — paying client)
- **Region:** `australiaeast`

## Step 0: Pre-Flight Validation

**CRITICAL: Before executing ANY deployment step, validate that this brief aligns with the actual codebase.** This brief was written from specifications, not from the running code. Discrepancies may exist.

Run ALL of the following checks and resolve any mismatches before proceeding:

```bash
# 1. Confirm you're on main and up to date
git status
git log --oneline -3

# 2. Confirm Azure CLI is logged in
az account show --query "{name:name, id:id}" -o table

# 3. Confirm deploy-bicep.sh exists, is executable, and check its usage/args
ls -la infra/deploy-bicep.sh
head -20 infra/deploy-bicep.sh

# 4. Confirm Bicep parameter directory and check an existing param file for format
ls infra/parameters/
cat infra/parameters/team.bicepparam 2>/dev/null || cat infra/parameters/demo.bicepparam 2>/dev/null

# 5. Confirm manage_tokens.py location and check its subcommands
find . -name "manage_tokens.py" -type f
python3 $(find . -name "manage_tokens.py" -type f | head -1) --help 2>/dev/null || true

# 6. Confirm the port FastAPI binds to (critical for health probes)
grep -rn "port\|8000\|8080" Dockerfile server/src/main.py 2>/dev/null

# 7. Confirm health endpoints that exist
grep -rn "health" server/src/main.py 2>/dev/null | grep -i "route\|app\.\|@"

# 8. Check if MCP_AUTH_TOKENS is referenced in Bicep templates
grep -rn "MCP_AUTH_TOKENS" infra/ 2>/dev/null

# 9. Verify token hashing — does validate_mcp_token hash incoming tokens?
grep -A5 "validate_mcp_token\|token_hash" server/src/main.py 2>/dev/null
```

### Validation Checklist

After running the above, confirm or fix:

- [ ] `deploy-bicep.sh` argument count matches Step 3 below (expected: 2 args — environment name + image tag)
- [ ] `.bicepparam` format matches the template in Step 1 below (compare with existing param file)
- [ ] `manage_tokens.py` path matches Step 6c below (expected: `server/scripts/manage_tokens.py`)
- [ ] `manage_tokens.py` subcommand is `create` with flags `--client`, `--email`, `--expires`
- [ ] FastAPI port matches Bicep health probe port (if mismatch, update Bicep or brief accordingly)
- [ ] Health endpoints `/health`, `/health/live`, `/health/ready` all exist in code
- [ ] Token hashing is single-hash (middleware hashes incoming token once with SHA256, DB stores that hash)
- [ ] `MCP_AUTH_TOKENS` is NOT set in Bicep templates (auth is DB-backed only)

**If ANY check fails:** Fix the discrepancy in this brief before continuing. Do NOT proceed with a known mismatch — this is a production client environment.

**If ALL checks pass:** Proceed to Step 1.

## Step 1: Create Parameter File

Create `infra/parameters/marshall.bicepparam`:

```
using '../main.bicep'

param environmentName = 'marshall'
param location = 'australiaeast'
param acrName = 'meetingintelacr20260116'
param sqlAdminObjectId = 'dff4aa0e-e9b5-4060-9a88-4947c5903b99'
param sqlAdminDisplayName = 'Caleb Lucas'
param azureTenantId = '12e7fcaa-f776-4545-aacf-e89be7737cf3'
param azureClientId = '90ce0113-054d-494d-a4e9-fcf8f0f9d07d'
param allowedUsers = 'john.marshall@myadvisor.co.nz,caleb.lucas@generationai.co.nz'
param corsOrigins = 'PLACEHOLDER_UPDATE_AFTER_DEPLOY'
param minReplicas = 1
```

**NOTE:** `azureClientId` is a dedicated app registration for Marshall (`90ce0113-054d-494d-a4e9-fcf8f0f9d07d`). The redirect URI needs updating post-deployment — see Step 5.

**NOTE:** This param file contains no secrets (JWT is passed via CLI at deploy time). Existing `.bicepparam` files (`team`, `demo`) are already committed and tracked in git — this one should be too.

## Step 2: Generate JWT Secret

Generate a unique JWT secret for John's environment. Do NOT reuse the existing environments' secrets.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Save this value** — you'll be prompted for it during deployment. Do NOT store it in any file.

## Step 3: Deploy Infrastructure

```bash
./infra/deploy-bicep.sh marshall
```

**PREREQUISITE:** The Docker image must already exist in ACR. Build and push first:

```bash
az acr build --registry meetingintelacr20260116 --image mi-marshall:$(git rev-parse --short HEAD) .
```

Then deploy:

```bash
./infra/deploy-bicep.sh marshall $(git rev-parse --short HEAD)
```

The script will:
1. Prompt for `JWT_SECRET` — paste the value from Step 2
2. Load `APP_INSIGHTS_CONNECTION` from `.env.deploy` if set, otherwise leave empty (Bicep's monitoring module auto-generates one)
3. Create resource group `meeting-intelligence-marshall-rg`
4. Deploy all Bicep modules (Container App, SQL Server, SQL Database, Key Vault, App Insights)

### Capture deployment outputs

After deployment completes, capture:

```bash
# Get the Container App FQDN
az containerapp show \
  --name mi-marshall \
  --resource-group meeting-intelligence-marshall-rg \
  --query "properties.configuration.ingress.fqdn" \
  -o tsv

# Get the managed identity principal ID
az containerapp show \
  --name mi-marshall \
  --resource-group meeting-intelligence-marshall-rg \
  --query "identity.principalId" \
  -o tsv

# Get App Insights connection string (for Key Vault update later)
az monitor app-insights component show \
  --app mi-marshall \
  --resource-group meeting-intelligence-marshall-rg \
  --query "connectionString" \
  -o tsv
```

## Step 4: Fix ACR Pull Role (If Needed)

The Bicep `container-app.bicep` configures `identity: 'system'` for the ACR registry, which may handle pulls automatically. However, Stream F found this sometimes requires an explicit role assignment. **Check if the Container App can pull images first** — if revisions fail with image pull errors, run the following:

```bash
# Get the managed identity principal ID (from Step 3 output)
PRINCIPAL_ID=$(az containerapp show \
  --name mi-marshall \
  --resource-group meeting-intelligence-marshall-rg \
  --query "identity.principalId" \
  -o tsv)

# Assign ACR Pull role
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "AcrPull" \
  --scope "/subscriptions/89333fc1-2427-4082-9368-d65612664da6/resourceGroups/meeting-intelligence-v2-rg/providers/Microsoft.ContainerRegistry/registries/meetingintelacr20260116"
```

Wait 1-2 minutes for the role to propagate, then restart the Container App revision:

```bash
az containerapp revision restart \
  --name mi-marshall \
  --resource-group meeting-intelligence-marshall-rg \
  --revision $(az containerapp revision list \
    --name mi-marshall \
    --resource-group meeting-intelligence-marshall-rg \
    --query "[0].name" -o tsv)
```

## Step 5: Update CORS Origins

Now that we have the FQDN, update the Container App's CORS origins:

```bash
FQDN=$(az containerapp show \
  --name mi-marshall \
  --resource-group meeting-intelligence-marshall-rg \
  --query "properties.configuration.ingress.fqdn" \
  -o tsv)

echo "Container App URL: https://$FQDN"
```

Update `infra/parameters/marshall.bicepparam` with the actual FQDN:

```
param corsOrigins = 'https://<FQDN>'
```

Then redeploy to apply the CORS change:

```bash
./infra/deploy-bicep.sh marshall $(git rev-parse --short HEAD)
```

### Update App Registration Redirect URI

The app registration was created with a placeholder redirect URI. Update it with the actual FQDN:

```bash
az ad app update \
  --id 90ce0113-054d-494d-a4e9-fcf8f0f9d07d \
  --web-redirect-uris "https://$FQDN/auth/callback"
```

## Step 6: SQL Database Setup

### 6a: Create Managed Identity User

The Container App's managed identity needs database access. Run this SQL on the new `marshall` database via **Azure Portal Query Editor** (Portal > SQL Database > Query Editor):

```sql
CREATE USER [mi-marshall] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [mi-marshall];
ALTER ROLE db_datawriter ADD MEMBER [mi-marshall];
```

### 6b: Run Auth Migration

Run the contents of `server/migrations/002_client_tokens.sql` on the marshall database via Azure Portal Query Editor. This creates the `ClientToken` and `OAuthClient` tables.

### 6c: Generate John's Auth Token

**IMPORTANT:** `manage_tokens.py` requires the Azure Python SDK which is NOT installed locally (only in Docker). Two options:

**Option A: Run via Docker (preferred)**
```bash
docker run --rm -it \
  -e AZURE_SQL_SERVER=<marshall-sql-server>.database.windows.net \
  -e AZURE_SQL_DATABASE=mi-marshall-db \
  meetingintelacr20260116.azurecr.io/mi-marshall:$(git rev-parse --short HEAD) \
  python scripts/manage_tokens.py create \
    --client "John Marshall" \
    --email "john.marshall@myadvisor.co.nz" \
    --expires 365
```

**Option B: Generate manually**

Generate a token and its SHA256 hash, then INSERT directly via Azure Portal:

```bash
# Generate a random token
python3 -c "
import secrets, hashlib
token = secrets.token_urlsafe(32)
token_hash = hashlib.sha256(token.encode()).hexdigest()
print(f'Plaintext token (GIVE TO JOHN): {token}')
print(f'Token hash (store in DB):       {token_hash}')
"
```

Then run this SQL on the marshall database via Azure Portal Query Editor:

```sql
INSERT INTO ClientToken (TokenHash, ClientName, ClientEmail, IsActive, CreatedBy, Notes)
VALUES (
  '<TOKEN_HASH_FROM_ABOVE>',
  'John Marshall',
  'john.marshall@myadvisor.co.nz',
  1,
  'cli-manual',
  'Initial token — first client deployment'
);
```

**CRITICAL:** Save the plaintext token securely. It is shown ONCE and cannot be recovered. This is what John will use in his Claude Desktop config.

**How token auth works:** The plaintext token is given to John. John's client (Claude Desktop, etc.) sends the plaintext token. The middleware hashes it once with SHA256 and looks up that hash in the `ClientToken` table. So the DB stores `SHA256(plaintext)` — a single hash.

## Step 7: Verify Health

```bash
FQDN=$(az containerapp show \
  --name mi-marshall \
  --resource-group meeting-intelligence-marshall-rg \
  --query "properties.configuration.ingress.fqdn" \
  -o tsv)

# Health check
curl -s "https://$FQDN/health"
# Expected: {"status":"healthy","transports":["sse","streamable-http"],"oauth":true}

# Readiness check (tests DB connection)
curl -s "https://$FQDN/health/ready"
# Expected: {"status":"ready","database":"connected"}
```

If health checks fail, check:
1. ACR Pull role was assigned (Step 4)
2. SQL managed identity user was created (Step 6a)
3. Container App logs: `az containerapp logs show --name mi-marshall --resource-group meeting-intelligence-marshall-rg`

## Step 8: Test Auth

Test that John's token works against the live environment. Use the **plaintext token** — the middleware hashes it to look up in the DB:

```bash
# Test MCP SSE connection (Claude Desktop transport)
curl -s "https://$FQDN/sse?token=<PLAINTEXT_TOKEN>" -H "Accept: text/event-stream" --max-time 5

# Test MCP Streamable HTTP (Copilot transport)
curl -s -X POST "https://$FQDN/mcp/<PLAINTEXT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Test Bearer token auth
curl -s "https://$FQDN/health" -H "Authorization: Bearer <PLAINTEXT_TOKEN>"
```

## Step 9: Prepare Client Configuration

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "meeting-intelligence": {
      "url": "https://<FQDN>/sse?token=<PLAINTEXT_TOKEN>"
    }
  }
}
```

### Copilot Studio

```
Endpoint URL: https://<FQDN>/mcp/<PLAINTEXT_TOKEN>
Transport: Streamable HTTP
```

### ChatGPT (OAuth 2.1 PKCE)

ChatGPT OAuth requires:
1. The Container App's OAuth endpoints are auto-configured at:
   - Authorization: `https://<FQDN>/oauth/authorize`
   - Token: `https://<FQDN>/oauth/token`
2. Register the connector in ChatGPT with these endpoints
3. John needs Developer Mode enabled in ChatGPT
4. Connector must be manually enabled in Tools menu per chat

### Web UI

```
URL: https://<FQDN>
Login: Azure AD (john.marshall@myadvisor.co.nz)
```

John's email must be in `ALLOWED_USERS` env var (already set in Step 1).

## Step 10: Document and Commit

1. Commit the `marshall.bicepparam` file (ensure no secrets are in it)
2. Record the deployment in the project status

```bash
git add infra/parameters/marshall.bicepparam
git commit -m "feat: add John Marshall production environment parameters"
git push
```

## Deliverables Checklist

- [ ] Resource group `meeting-intelligence-marshall-rg` created
- [ ] Container App running with `minReplicas=1`
- [ ] SQL Server + Database deployed
- [ ] Key Vault with JWT_SECRET stored
- [ ] ACR Pull role assigned
- [ ] SQL managed identity user created
- [ ] Auth tables migrated (002_client_tokens.sql)
- [ ] John's auth token generated and stored
- [ ] CORS origins updated
- [ ] Health check passing (`/health` + `/health/ready`)
- [ ] Auth verified (SSE + Streamable HTTP + Bearer)
- [ ] Client configs prepared (Claude Desktop, Copilot, ChatGPT, Web UI)
- [ ] Parameter file committed

## Rollback

If anything goes wrong:

```bash
# Delete the entire resource group (removes everything)
az group delete --name mi-marshall-rg --yes --no-wait
```

This is a clean deployment — no data to lose. Can re-run from Step 1.

---

*Brief version: 1.1 — 10 Feb 2026 (fixed: container app name, token hashing, ACR pull, image build step)*
*Environment: marshall | Client: John Marshall | Status: Production*

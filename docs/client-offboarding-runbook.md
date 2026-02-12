# Client Offboarding Runbook

**Meeting Intelligence System**
**Version:** 1.0 — 12 February 2026
**Owner:** Caleb Lucas

---

## When to Use

When a client leaves the service, or requests their data be removed.

## Prerequisites

- Azure CLI authenticated (`az login`)
- Access to the client's Azure SQL database
- Access to the client's resource group

---

## Step 1: Export Client Data

Run the export script against the client's database:

```bash
cd server
uv run python -m scripts.export_client_data \
    --server genai-sql-server.database.windows.net \
    --database mi-<client> \
    --output ./exports/<client>-$(date +%Y-%m-%d)
```

This creates:
- `meeting.json` — All meetings with transcripts and summaries
- `action.json` — All action items
- `decision.json` — All decisions
- `export-manifest.json` — Export metadata (date, row counts)

---

## Step 2: Deliver Data to Client

1. Zip the export directory
2. Send to client via secure channel (encrypted email or shared drive)
3. Get written confirmation from client that they have received their data

---

## Step 3: Revoke Access

### Revoke MCP Tokens

```bash
cd server
uv run python -m scripts.manage_tokens list     # Find client's token IDs
uv run python -m scripts.manage_tokens revoke <token_id>
```

### Remove from ALLOWED_USERS

Update the environment's Bicep parameter file to remove the client's email(s) from `allowedUsers`.

### Revoke OAuth Clients

Any ChatGPT/Claude OAuth registrations will expire naturally (30-day refresh tokens). For immediate revocation, remove from the `OAuthClient` table:

```sql
UPDATE OAuthClient SET IsActive = 0
WHERE ClientId IN (SELECT ClientId FROM OAuthClient WHERE ClientName LIKE '%<client>%');
```

---

## Step 4: Teardown Resources

### Delete the Resource Group

This removes the Container App, Container Apps Environment, Key Vault, monitoring resources, and alert rules:

```bash
az group delete \
    --name meeting-intelligence-<client>-rg \
    --yes --no-wait
```

### Delete the SQL Database

The database is in a shared SQL server, so delete just the database (not the server):

```bash
az sql db delete \
    --server genai-sql-server \
    --name mi-<client> \
    --resource-group rg-generationAI-Internal \
    --yes
```

### Clean Up ACR Images

Remove client-specific container images:

```bash
az acr repository delete \
    --name meetingintelacr20260116 \
    --image mi-<client> \
    --yes
```

### Remove Bicep Parameter File

```bash
rm infra/parameters/<client>.bicepparam
git add -A && git commit -m "chore: remove <client> environment after offboarding"
```

---

## Step 5: Verification Checklist

- [ ] Client confirmed receipt of exported data
- [ ] MCP tokens revoked
- [ ] Email removed from ALLOWED_USERS
- [ ] Resource group deleted
- [ ] SQL database deleted
- [ ] ACR images cleaned up
- [ ] Bicep parameter file removed from repo
- [ ] Client removed from `ENVIRONMENTS` dict in `scripts/migrate.py`
- [ ] Client removed from `deploy-all.sh` CLIENT_ENVS list
- [ ] Updated CLAUDE.md Environments table

---

## Data Retention

After client confirmation of data receipt:
- Delete the local export files
- No data is retained after offboarding unless required by legal agreement

---

*This runbook assumes the standard per-client deployment model (separate resource group, separate database, shared SQL server and ACR).*

# DOC4 — Break-glass / Ops Runbook

**Meeting Intelligence System**
**Version:** 1.0 — 27 February 2026
**Owner:** Caleb Lucas

The "2am something is broken" doc. Keep this short and actionable.

---

## Escalation Contacts

| Role | Person | Contact | When |
|------|--------|---------|------|
| Primary on-call | Caleb Lucas | caleb.lucas@generationai.co.nz | All incidents |
| Business owner | Mark (Generation AI) | Via Caleb | Client-facing outage >15 min |
| Infrastructure | Craig Corfield (CorIT) | Via Caleb | Azure subscription / network issues |

**Support hours:** NZ business hours (Mon-Fri 8am-6pm NZST). After-hours: best-effort within 2 hours for critical alerts.

---

## 1. Rollback a Bad Deployment

**When:** Error rate >5% after deploy, health probe failures, MCP tools returning errors.
**Time to fix:** <5 minutes.

```bash
# List revisions — find the last working one
az containerapp revision list -n mi-<env> -g meeting-intelligence-<env>-rg \
  --query "[].{name:name, active:properties.active, created:properties.createdTime}" -o table

# Activate the previous revision
az containerapp revision activate -n mi-<env> -g <rg> --revision <PREVIOUS>

# Route all traffic to it
az containerapp ingress traffic set -n mi-<env> -g <rg> --revision-weight <PREVIOUS>=100

# Verify
curl -sf https://<FQDN>/health/ready | jq

# Deactivate the broken revision
az containerapp revision deactivate -n mi-<env> -g <rg> --revision <BAD>
```

**Note:** Rollback does NOT affect Key Vault secrets or database schema. If the issue is a schema migration, you need PITR (see below).

---

## 2. Restore Database (PITR)

**When:** Accidental data deletion, schema corruption, bad migration.
**Time to fix:** ~30 minutes.
**RPO:** 15 minutes (Azure SQL Basic tier, 7-day retention).

```bash
# Pick a restore point (before the incident)
RESTORE_TIME="2026-02-27T02:00:00Z"

# Restore to a new database
az sql db restore \
  --server mi-<env>-sql \
  --resource-group meeting-intelligence-<env>-rg \
  --name mi-<env> \
  --dest-name mi-<env>-restored \
  --time "$RESTORE_TIME"

# Verify the restored database (spot-check row counts)
sqlcmd -S mi-<env>-sql.database.windows.net -d mi-<env>-restored \
  -G --authentication-method=ActiveDirectoryDefault \
  -Q "SELECT 'Meetings', COUNT(*) FROM Meeting UNION ALL SELECT 'Actions', COUNT(*) FROM Action UNION ALL SELECT 'Decisions', COUNT(*) FROM Decision"
```

**To swap in the restored database:**

```bash
# Rename current (broken) database
az sql db rename --server mi-<env>-sql -g <rg> --name mi-<env> --new-name mi-<env>-broken

# Rename restored database to the expected name
az sql db rename --server mi-<env>-sql -g <rg> --name mi-<env>-restored --new-name mi-<env>

# Restart the container to pick up the new database
az containerapp revision restart -n mi-<env> -g <rg> --revision <current-revision>

# Verify
curl -sf https://<FQDN>/health/ready | jq
```

**Tested:** 9 Feb 2026. Restore completed in <5 minutes. All data intact (2 meetings, 26 actions, 6 decisions verified).

---

## 3. Revoke a Compromised Token

**When:** Token leaked, user device lost, account compromise, user offboarding.
**Time to fix:** <1 minute (+ up to 5 min cache lag).

### Via Web UI (user self-service)

Settings → find the token → click Revoke.

### Via CLI (admin)

```bash
# List tokens to find the ID
cd server && AZURE_SQL_SERVER=mi-<env>-sql.database.windows.net \
  CONTROL_DB_NAME=mi-<env>-control \
  uv run python scripts/manage_tokens.py list

# Revoke by token ID
cd server && AZURE_SQL_SERVER=mi-<env>-sql.database.windows.net \
  CONTROL_DB_NAME=mi-<env>-control \
  uv run python scripts/manage_tokens.py revoke --token-id <ID>
```

**Cache warning:** The auth layer caches token lookups for 5 minutes. A revoked token may still work for up to 5 minutes after revocation. For immediate invalidation during a security incident, restart the container:

```bash
az containerapp revision restart -n mi-<env> -g <rg> --revision <current-revision>
```

---

## 4. Full Environment Rebuild

**When:** Catastrophic failure, corrupted infrastructure, regional outage.
**Time to fix:** ~60 minutes.
**Requires:** Parameter file in git, `.env.deploy` present.

```bash
# Everything is codified in Bicep — deploy from scratch
./infra/deploy-new-client.sh <client-name>
```

Then restore the database from PITR (Section 2 above) and swap it in.

For a regional outage, deploy to an alternate region by changing `location` in the parameter file. DNS will need updating.

---

## 5. Alert Response Quick Reference

All alerts email caleb.lucas@generationai.co.nz. 7 alert rules deployed via Bicep per environment.

| Alert | First action |
|-------|-------------|
| **5xx errors** | Check container logs: `az containerapp logs show -n mi-<env> -g <rg> --tail 50` |
| **Replica down** | Check revision status: `az containerapp revision list -n mi-<env> -g <rg> -o table` |
| **Auth failure spike** | Check for brute force — rate limiting (120/min MCP, 60/min API) should contain it. If token compromised, revoke (Section 3). |
| **High response time** | Check if database auto-pause is resuming (expected 2-5s on first request). If sustained, check DTU utilisation in portal. |
| **Container restarts** | Crash loop — check system logs: `az containerapp logs show -n mi-<env> -g <rg> --type system` |
| **High CPU/memory** | Auto-scaler should handle it (max 10 replicas). If at max, increase resources in Bicep. |

---

## 6. Client Communication Template

Use when client-facing downtime exceeds 15 minutes:

> **Subject:** Meeting Intelligence — Service Disruption
>
> Hi [Client Name],
>
> We're aware of an issue affecting the Meeting Intelligence service. Our team is actively investigating.
>
> **Impact:** [e.g., "MCP tool calls may be timing out"]
> **Started:** [Time] NZST
> **Status:** Investigating / Identified / Resolved
>
> We'll provide an update within [30 minutes / 1 hour].
>
> Regards,
> Caleb Lucas — Generation AI

---

## Recovery Targets

| Scenario | RPO | RTO |
|----------|-----|-----|
| Bad deployment | 0 (no data loss) | 5 min (rollback) |
| Database corruption | 15 min | 30 min (PITR + swap) |
| Full environment rebuild | 15 min (PITR) | 60 min |
| Regional outage | 1 hour (geo backup) | 4 hours (manual redeploy) |

---

*This runbook references `incident-response-playbook.md`, `sla-rpo-rto.md`, and `rollback-procedure.md` in the same `docs/` directory for extended detail. Keep all four in sync.*

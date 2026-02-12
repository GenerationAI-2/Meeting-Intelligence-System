# Incident Response Playbook

**Meeting Intelligence System**
**Version:** 1.0 — 12 February 2026
**Owner:** Caleb Lucas

---

## Alert Types and Severity

| Alert | Severity | Source | Trigger |
|-------|----------|--------|---------|
| 5xx Error Spike | Critical | Azure Monitor | >5 server errors in 5 minutes |
| Replica Down | Critical | Azure Monitor | 0 replicas (always-on envs only) |
| Auth Failure Spike | Critical | Log Analytics (KQL) | >20 401s in 5 minutes |
| High Response Time | Warning | Azure Monitor | Avg >5s over 5 minutes |
| Excessive Restarts | Warning | Azure Monitor | >3 restarts in 5 minutes |
| High CPU | Warning | Azure Monitor | >90% of allocated CPU |
| High Memory | Warning | Azure Monitor | >90% of allocated memory |

---

## Who Gets Notified

| Role | Person | Contact | Notified |
|------|--------|---------|----------|
| Primary on-call | Caleb Lucas | caleb.lucas@accretiveai.com | All alerts |
| Business owner | Mark (Generation AI) | Via Caleb | Critical only, during business hours |

---

## Response Procedures

### 5xx Error Spike

**Impact:** Clients experiencing failures on MCP tool calls or web UI.

1. Check Container App logs:
   ```bash
   az containerapp logs show -n mi-<env> -g meeting-intelligence-<env>-rg --tail 50
   ```
2. Check if database is accessible:
   ```bash
   curl -s https://<fqdn>/health/ready
   ```
3. If database is down (auto-paused): Wait 30-60 seconds for resume. If still failing, check Azure SQL portal for service health.
4. If application error: Check logs for stack traces. Redeploy last known good image:
   ```bash
   ./infra/deploy-bicep.sh <env> <last-good-tag>
   ```
5. If widespread: Check Azure service health dashboard.

### Replica Down (Always-On Environments)

**Impact:** Client environment completely unavailable.

1. Check Container App revision status:
   ```bash
   az containerapp revision list -n mi-<env> -g meeting-intelligence-<env>-rg -o table
   ```
2. If revision is in failed state: Check logs for crash reason. Common causes:
   - Database connection failure (check SQL server status)
   - Missing/invalid environment variable (check Key Vault secrets)
   - Image pull failure (check ACR access)
3. Restart the revision:
   ```bash
   az containerapp revision restart -n mi-<env> -g meeting-intelligence-<env>-rg --revision <revision-name>
   ```
4. If restart doesn't help: Redeploy with the same image tag to force a new revision.

### Auth Failure Spike (Possible Brute Force)

**Impact:** Potential credential stuffing or token brute force attack.

1. Check Log Analytics for source IPs:
   ```
   ContainerAppConsoleLogs_CL
   | where Log_s has "401" or Log_s has "Unauthorized"
   | summarize count() by bin(TimeGenerated, 1m)
   | order by TimeGenerated desc
   ```
2. If from a single IP: Monitor. Azure Container Apps has no built-in IP blocking. Rate limiting (20/min for OAuth) provides some protection.
3. If tokens may be compromised: Rotate affected client tokens:
   ```bash
   cd server && uv run python -m scripts.manage_tokens revoke <token_id>
   ```
4. Notify affected client if their token was compromised.

### High Response Time

**Impact:** Degraded user experience, MCP tool calls timing out.

1. Check if this coincides with database auto-pause resume (first request after idle period takes 2-5s). If so, this is expected — no action needed.
2. Check database DTU utilisation in Azure portal. If DTUs maxed out, consider scaling the database tier.
3. Check for expensive queries in Application Insights:
   - Portal > Application Insights > Performance > Dependencies
4. If sustained: Check if there's unusual load (potential DoS). Rate limiting should catch this.

### Excessive Restarts

**Impact:** Service instability, potential data loss for in-progress requests.

1. This usually indicates a crash loop. Check logs for the crash reason:
   ```bash
   az containerapp logs show -n mi-<env> -g meeting-intelligence-<env>-rg --type system
   ```
2. Common causes:
   - OOM kill (check memory alert — may need to increase memory allocation)
   - Missing required environment variable
   - Database connectivity issue on startup
3. If OOM: Increase memory in `container-app.bicep` and redeploy.
4. If env var issue: Check Key Vault secrets and Container App configuration.

### High CPU / Memory

**Impact:** Performance degradation, risk of OOM kills.

1. Check if this is transient (burst of requests) or sustained.
2. If sustained: The auto-scaler should add replicas. Check scale rules:
   ```bash
   az containerapp show -n mi-<env> -g meeting-intelligence-<env>-rg --query properties.template.scale
   ```
3. If already at maxReplicas (10): Consider increasing resource allocation in `container-app.bicep`.
4. Monitor for resolution. CPU/memory alerts auto-mitigate when the metric drops below threshold.

---

## Escalation Path

| Level | Condition | Action |
|-------|-----------|--------|
| L1 | Any alert fires | Caleb investigates within 30 minutes (NZ business hours) |
| L2 | Client-facing outage >15 min | Caleb notifies Mark. Begins client communication. |
| L3 | Data loss or security breach | Caleb + Mark. Follow data breach notification process per client agreement. |

---

## Client Communication Template

Use when a client-facing environment experiences downtime >15 minutes:

> **Subject:** Meeting Intelligence — Service Disruption
>
> Hi [Client Name],
>
> We're aware of an issue affecting the Meeting Intelligence service. Our team is actively investigating.
>
> **Impact:** [Brief description — e.g., "MCP tool calls may be timing out"]
> **Started:** [Time] NZST
> **Status:** Investigating / Identified / Resolved
>
> We'll provide an update within [30 minutes / 1 hour].
>
> Regards,
> Caleb Lucas — Generation AI

---

## Post-Incident Review

After any Critical alert that resulted in client impact:

1. **Within 24 hours:** Write a brief incident summary:
   - What happened
   - Timeline
   - Root cause
   - What we did to fix it
   - What we'll do to prevent it
2. **Within 1 week:** Implement any preventive measures identified.
3. **Log:** Add to decision log if any architectural changes are needed.

---

*Keep this playbook simple. This is a 1-3 person operation, not enterprise ITIL.*

# NOW Items Implementation Prompt

**For:** Agent implementing critical architecture review fixes

**Date:** 5 February 2026

**Goal:** Make Meeting Intelligence client-ready by addressing all NOW items from the architecture review.

---

## Context

Architecture review identified 4 critical gaps that must be fixed before client deployment. You have full access to the codebase. Implement all fixes.

**Reference:** `docs/architecture-review-findings.md`

---

## Tasks (Implement All)

### 1. Add Application Insights SDK

**Why:** Currently no production observability. Can't diagnose issues.

**Implementation:**
1. Add `azure-monitor-opentelemetry` to `server/requirements.txt`
2. Configure in `server/src/main.py` or `server/src/config.py`
3. Use connection string from environment variable `APPLICATIONINSIGHTS_CONNECTION_STRING`
4. Ensure it captures:
   - HTTP requests (FastAPI middleware)
   - Exceptions
   - Dependencies (SQL calls)
   - Custom events (tool calls)

**Example:**
```python
from azure.monitor.opentelemetry import configure_azure_monitor

configure_azure_monitor(
    connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
)
```

**Test:** After deployment, verify traces appear in Azure Portal → Application Insights

---

### 2. Replace print() with Logging Module

**Why:** 19 print() statements. No log levels, no structured logging, logs lost in container restarts.

**Implementation:**
1. Create `server/src/logging_config.py` with structured logging setup
2. Replace all `print()` calls with appropriate log levels:
   - `logger.info()` for normal operations
   - `logger.warning()` for issues that don't stop execution
   - `logger.error()` for errors
   - `logger.debug()` for verbose debugging
3. Include context in logs (request IDs, user info where available)
4. Integrate with Application Insights

**Files to update:**
- `server/src/main.py` — multiple print statements
- `server/src/api.py` — auth logging, request logging
- `server/src/config.py` — startup diagnostics

**Example:**
```python
import logging

logger = logging.getLogger(__name__)

# Instead of: print(f"[AUTH] Token validated successfully")
logger.info("Token validated", extra={"user": user_email})
```

---

### 3. Configure Health Probes in deploy.sh

**Why:** Container Apps can't detect unhealthy instances. No automatic restart on failure.

**Implementation:**
1. Add liveness probe to `deploy.sh` Container Apps configuration
2. Add readiness probe to `deploy.sh`
3. Use the existing `/health` endpoint (or `/api/health`)

**Add to deploy.sh (az containerapp create/update):**
```bash
--probe-liveness-path "/health" \
--probe-liveness-port 8000 \
--probe-liveness-initial-delay 10 \
--probe-liveness-period 30 \
--probe-readiness-path "/health" \
--probe-readiness-port 8000 \
--probe-readiness-initial-delay 5 \
--probe-readiness-period 10
```

**Verify:** `/health` endpoint returns 200 when healthy, non-200 when not.

---

### 4. Enable Azure SQL Auditing

**Why:** No audit trail for database access. Compliance requirement for enterprise.

**Implementation:**
This is an Azure configuration, not code. Create a script or document the steps:

1. Enable auditing via Azure CLI:
```bash
az sql server audit-policy update \
  --resource-group genai-infra \
  --server genai-sql-server \
  --state Enabled \
  --storage-account <storage-account-name> \
  --retention-days 90
```

2. Or enable via Azure Portal:
   - SQL Server → Auditing → Enable
   - Choose storage account for logs
   - Set retention (90 days recommended)

**Deliverable:** Create `scripts/enable-sql-auditing.sh` with the Azure CLI commands.

---

## Deployment

After implementing all changes:

1. Test locally:
```bash
cd server && uv run python -m src.main --http
# Verify /health returns 200
# Verify logs are structured (not print statements)
```

2. Deploy to team instance:
```bash
./deploy.sh team
```

3. Verify in Azure Portal:
   - Application Insights shows incoming requests
   - Container Apps shows health probes configured
   - SQL Auditing is enabled

---

## Definition of Done

- [ ] Application Insights SDK added and configured
- [ ] All print() replaced with logging module (0 print statements in src/)
- [ ] Health probes configured in deploy.sh
- [ ] SQL Auditing script created
- [ ] Deployed to team instance
- [ ] Verified working in Azure Portal

---

## Environment Variables to Add

Update `.env.deploy.template`:
```
APPLICATIONINSIGHTS_CONNECTION_STRING=<from-azure-portal>
```

---

## Out of Scope (SOON items, not NOW)

- Key Vault integration (do later)
- OAuth persistence to database (do later)
- Retry logic (do later)
- GitHub Actions CI/CD (do later)

---

*Focus on the 4 NOW items only. Ship these, then we're client-ready.*

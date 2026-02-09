# Rollback Procedure — Meeting Intelligence

## When to Rollback

- Error rate >5% sustained for 5+ minutes after deployment
- Health probe failures on /health/ready
- P95 response time >10 seconds
- MCP tool calls returning errors

## Steps

### 1. Identify Previous Revision

```bash
az containerapp revision list \
  --name meeting-intelligence-[ENV] \
  --resource-group meeting-intelligence-[ENV]-rg \
  --query "[].{name:name, active:properties.active, created:properties.createdTime}" \
  -o table
```

### 2. Activate Previous Revision

```bash
az containerapp revision activate \
  --name meeting-intelligence-[ENV] \
  --resource-group meeting-intelligence-[ENV]-rg \
  --revision [PREVIOUS_REVISION_NAME]
```

### 3. Route Traffic to Previous Revision

```bash
az containerapp ingress traffic set \
  --name meeting-intelligence-[ENV] \
  --resource-group meeting-intelligence-[ENV]-rg \
  --revision-weight [PREVIOUS_REVISION_NAME]=100
```

### 4. Verify Rollback

```bash
curl -s https://[FQDN]/health/ready | jq
# Expected: {"status": "ready", "database": "connected"}
```

### 5. Deactivate Bad Revision

```bash
az containerapp revision deactivate \
  --name meeting-intelligence-[ENV] \
  --resource-group meeting-intelligence-[ENV]-rg \
  --revision [BAD_REVISION_NAME]
```

## Expected Timeline

| Step | Duration |
|------|----------|
| Identify previous revision | 1 minute |
| Activate + route traffic | 2 minutes |
| Verify health | 1 minute |
| **Total** | **<5 minutes** |

## Notes

- Container Apps keeps previous revisions available for rollback
- Rollback does NOT affect Key Vault secrets or database schema
- If the issue is a database migration, rollback requires manual SQL intervention
- After rollback, investigate root cause before re-deploying

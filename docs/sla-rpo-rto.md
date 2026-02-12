# Service Level Commitments

**Meeting Intelligence System**
**Version:** 1.0 — 12 February 2026
**Owner:** Caleb Lucas
**Status:** Draft — targets to be confirmed by Caleb before inclusion in client agreements

---

## Availability

| Metric | Target | Basis |
|--------|--------|-------|
| Monthly uptime | 99.5% | Allows ~3.6 hours downtime/month |
| Planned maintenance windows | NZ business hours notice | Deploys cause <30s interruption |

**Measurement:** Availability = (total minutes - downtime minutes) / total minutes. Measured per calendar month per client environment.

**Exclusions:**
- Scheduled maintenance with 24-hour notice
- Azure platform outages (covered by Microsoft's SLA)
- Client-side network issues
- Cold start delay (2-5 seconds) after scale-to-zero for internal environments

---

## Recovery Point Objective (RPO)

| Scenario | RPO | Mechanism |
|----------|-----|-----------|
| Database corruption / accidental deletion | 15 minutes | Azure SQL Point-in-Time Restore (PITR) |
| Regional outage | 1 hour | Geo-replicated backups (Azure SQL Basic tier) |
| Complete data loss | 24 hours | Last full daily backup |

**Azure SQL PITR:** Automatic backups with 7-day retention (Basic tier). Restore to any point in the last 7 days with up to 5-minute granularity.

**Note:** Azure SQL Basic tier does not support geo-replication or long-term backup retention. For clients requiring lower RPO, upgrade to Standard tier (~$20 AUD/month additional).

---

## Recovery Time Objective (RTO)

| Scenario | RTO | Procedure |
|----------|-----|-----------|
| Application crash / bad deployment | 10 minutes | Redeploy last known good image via `deploy-bicep.sh` |
| Database restore (PITR) | 30 minutes | Azure portal or CLI restore to new database, update connection |
| Full environment rebuild | 60 minutes | Bicep IaC redeploy from scratch (all infrastructure is codified) |
| Regional outage | 4 hours | Deploy to alternate region (manual process, requires new DNS) |

---

## Support Hours

| Tier | Hours | Response Time |
|------|-------|---------------|
| Critical (service down) | NZ business hours (Mon-Fri 8am-6pm NZST) | 30 minutes |
| Warning (degraded) | NZ business hours | 2 hours |
| Non-urgent | NZ business hours | Next business day |

**After-hours:** Critical alerts are emailed. Best-effort response within 2 hours. No formal after-hours SLA at current scale.

---

## Monitoring and Alerting

The following alerts are configured (deployed via Bicep to all environments):

| Alert | Threshold | Notification |
|-------|-----------|--------------|
| 5xx errors | >5 in 5 min | Email (immediate) |
| Response time | Avg >5s | Email (immediate) |
| Replica down | 0 replicas (always-on only) | Email (immediate) |
| Container restarts | >3 in 5 min | Email (immediate) |
| CPU usage | >90% | Email (immediate) |
| Memory usage | >90% | Email (immediate) |
| Auth failure spike | >20 401s in 5 min | Email (immediate) |

---

## Infrastructure Guarantees

| Component | Underlying SLA | Source |
|-----------|---------------|--------|
| Azure Container Apps | 99.95% | Microsoft SLA |
| Azure SQL Database (Basic) | 99.99% | Microsoft SLA |
| Azure Key Vault | 99.99% | Microsoft SLA |

Our 99.5% target accounts for application-level issues on top of the underlying platform SLAs.

---

## Cost of Higher SLAs

If a client requires higher availability:

| Upgrade | Additional Cost | Improvement |
|---------|----------------|-------------|
| Always-on replicas (minReplicas=1) | ~$10 AUD/month | Eliminates cold start, faster recovery |
| Azure SQL Standard tier | ~$20 AUD/month | Longer backup retention, geo-replication option |
| Multi-region deployment | ~$60 AUD/month | Regional failover, lower RTO for regional outages |
| 24/7 on-call support | TBD (staffing cost) | After-hours critical response |

---

*These commitments apply to the Meeting Intelligence managed service. Self-hosted deployments are not covered.*

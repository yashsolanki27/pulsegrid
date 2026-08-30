RESOLVED [Phase 4]: Severity mapping -- LogPulse TriageRequest accepts only log_text (no severity field).
PulseGrid internal severity labels (order-no-invoice=high etc.) are not sent to LogPulse.
Confirmed via live Swagger test. See PulseGrid-Agent-Harness-Spec-v2.md section 8.

RESOLVED [Phase 4]: LogPulse real API contract confirmed via live Swagger test.
Endpoint: POST https://log-pulse.up.railway.app/triage, no auth, {log_text} only.
See PulseGrid-Agent-Harness-Spec-v2.md section 8 for full contract details.

---

RESOLVED [Phase 7 / access-control]: CRM/ERP reachability from Railway — Option A deployed
Logged: 2026-08-28
Resolved: 2026-08-31

## Resolution

Option A was chosen and implemented:
  - crm-service deployed to Railway (crm-service/railway.json + Dockerfile).
    Public URL: https://crm-service-production-6f6c.up.railway.app — HTTP 200 confirmed.
  - erp-service deployed to Railway (erp-service/railway.json + Dockerfile).
    Public URL: https://erp-service-production-d446.up.railway.app — HTTP 200 confirmed.
  - Shared Railway Postgres (single instance, two databases: crm + erp).
    Host: turntable.proxy.rlwy.net:17746
  - crm database: migrated (0001_initial) + seeded (10 customers, 8 orders, 7 tickets).
  - erp database: migrated (0001_initial + 0002_accounts_invoice_enum_inventory_check)
    + seeded (5 accounts, 6 invoices, 8 inventory items).
  - access-control lifespan updated: warns if CRM/ERP DB URLs still point to localhost.
  - dashboard.html: no change needed — already renders live data when mismatch_error is None.

## Owner action still required (cannot be done by agent)

Set these env vars on the access-control Railway service (Railway dashboard → service →
Variables):
  CRM_DATABASE_URL  = postgresql+psycopg://postgres:<pass>@turntable.proxy.rlwy.net:17746/crm
  ERP_DATABASE_URL  = postgresql+psycopg://postgres:<pass>@turntable.proxy.rlwy.net:17746/erp
  CRM_SERVICE_URL   = https://crm-service-production-6f6c.up.railway.app
  ERP_SERVICE_URL   = https://erp-service-production-d446.up.railway.app

Once set, all three dashboard sections (Reconciliation Mismatches, Service Health,
Sync Match Ratio) will be live in the hosted deployment.


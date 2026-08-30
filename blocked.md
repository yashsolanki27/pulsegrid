RESOLVED [Phase 4]: Severity mapping -- LogPulse TriageRequest accepts only log_text (no severity field).
PulseGrid internal severity labels (order-no-invoice=high etc.) are not sent to LogPulse.
Confirmed via live Swagger test. See PulseGrid-Agent-Harness-Spec-v2.md section 8.

RESOLVED [Phase 4]: LogPulse real API contract confirmed via live Swagger test.
Endpoint: POST https://log-pulse.up.railway.app/triage, no auth, {log_text} only.
See PulseGrid-Agent-Harness-Spec-v2.md section 8 for full contract details.

---

OPEN [Phase 7 / access-control]: CRM/ERP reachability from Railway — architecture decision required
Logged: 2026-08-28

## Context

access-control is deployed to Railway (root railway.json → access-control/Dockerfile).
Its dashboard has three data sources:
  1. Direct DB reads (CRM_DATABASE_URL + ERP_DATABASE_URL) → mismatch count
  2. HTTP /health pings (CRM_SERVICE_URL + ERP_SERVICE_URL) → service health section
  3. LogPulse /history → triage log (already reachable; log-pulse.up.railway.app is public)

Sources 1 and 2 are both dead in production because crm-service, erp-service, and their
Postgres instances exist ONLY in local Docker Compose — there is no Railway deployment,
no cloud host, and no publicly reachable URL for either service.

## Evidence

- crm-service/docker-compose.yml: single compose file, no railway.json, no cloud config.
- erp-service/docker-compose.yml: same — local only.
- No railway.json exists in crm-service/ or erp-service/.
- No Dockerfiles in crm-service/ or erp-service/ reference any cloud entrypoint beyond
  local defaults.
- access-control/app/config.py defaults:
    CRM_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/crm"
    ERP_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/erp"
    CRM_SERVICE_URL  = "http://localhost:8000"
    ERP_SERVICE_URL  = "http://localhost:8001"
  → These localhost defaults are unreachable from a Railway container.
  → No overrides are set as Railway env vars (no railway.json variables block in
    crm-service/ or erp-service/ to reference).
- access-control/app/main.py lifespan logs CONFIG ERROR at startup when CRM_DATABASE_URL
  is unset — but the service still starts and degrades gracefully (mismatch section
  shows error, health pings show "unreachable").

## What needs a decision

This is a deployment-scope decision, not a bug. Two options:

OPTION A — Deploy crm-service + erp-service (+ their Postgres DBs) to Railway
  - Add railway.json to crm-service/ and erp-service/ (mirrors access-control pattern).
  - Provision Railway Postgres plugin instances for each service (or use Railway's
    shared Postgres with separate databases).
  - Set CRM_DATABASE_URL / ERP_DATABASE_URL / CRM_SERVICE_URL / ERP_SERVICE_URL as
    Railway env vars on the access-control service, pointing at the Railway-internal
    private network URLs (e.g. crm-service.railway.internal:8000).
  - All three dashboard sections become live in production.
  - Implication: crm-service and erp-service become long-running Railway services with
    persistent managed DBs — this changes the project's Railway bill and operational
    footprint. CRM Phase 1 checklist is also still partially open (SPECS.md shows
    Phase 1 unchecked) — unclear if that matters for a deploy.

OPTION B — Keep crm-service + erp-service local-only; accept degraded dashboard in prod
  - Explicitly document the mismatch-count section and health-ping section as
    "dev/demo only — not available in the Railway deployment."
  - Remove CRM_DATABASE_URL / ERP_DATABASE_URL from the Railway startup validation
    (or lower to WARNING, not CONFIG ERROR) so logs are clean.
  - Update dashboard.html to display a permanent "local-only — not available in hosted
    deployment" notice instead of a transient error.
  - Tech-debt-tracker.md gets a "v1 scope limit" entry.
  - LogPulse /history section remains live; the dashboard is not entirely useless.

## Waiting for: owner decision on Option A vs Option B before any code or config changes.


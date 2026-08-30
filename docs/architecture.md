# Architecture

Modular monolith of independent services — not a single monolith, not full microservices with a message bus.

## Components

- `crm-service` — customers, orders, tickets
- `erp-service` — invoices, inventory, accounts
- `integration-sync` — logic inside crm-service that calls erp-service on order creation (not a standalone service)
- `reconciliation-job` — standalone scheduled script, reads both DBs directly
- `api-health-monitor` — Postman/Newman + GitHub Actions, not a running service
- `observability-stack` — Prometheus/Grafana/Loki/Alertmanager + a small webhook receiver service
- `access-control` — thin auth-gated dashboard service
- `pulsegrid_common` — shared library (just the LogPulse HTTP client)

## Connections

- `integration-sync` (inside `crm-service`) calls `erp-service` on order creation.
- `reconciliation-job` reads both databases (CRM and ERP) directly.
- `pulsegrid_common` is imported by `reconciliation-job`, `api-health-monitor`'s report script, and the webhook receiver.

## Hosted Railway URLs (confirmed 2026-08-31)

- `crm-service`    → https://crm-service-production-6f6c.up.railway.app
- `erp-service`    → https://erp-service-production-d446.up.railway.app
- `access-control` → https://pulsegrid-dashboard.up.railway.app

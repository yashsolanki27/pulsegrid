# PulseGrid

A CRM/ERP portfolio application demonstrating enterprise integration patterns, observability, and identity-based access control — built as a project for hands-on practice with Application Support and Functioneel Beheerder workflows.

---

## What it does

PulseGrid simulates a realistic business environment where a CRM system (customers, orders, tickets) and an ERP system (invoices, inventory, accounts) are kept in sync — imperfectly, by design. A scheduled reconciliation job detects the ~10% intentional sync gap and routes those discrepancies to **LogPulse**, an AI-assisted triage service that classifies errors and suggests root causes. The whole system is observable via a Prometheus/Grafana/Loki stack, and access to the operations dashboard is gated behind **Azure AD (Microsoft Entra ID)** login.

---

## Architecture

Modular monolith — eight components that communicate via HTTP or direct DB reads, no message broker:

| Component | Role |
|---|---|
| `crm-service` | FastAPI service — customers, orders, tickets (PostgreSQL) |
| `erp-service` | FastAPI service — invoices, inventory, accounts (PostgreSQL) |
| `integration-sync` | Logic inside crm-service: triggers ERP invoice creation on order, ~10% intentional silent failure |
| `reconciliation-job` | Scheduled Python script: reads both DBs, detects mismatches, reports to LogPulse |
| `api-health-monitor` | Postman/Newman suite on GitHub Actions (cron, every 15 min): checks all endpoints, reports failures to LogPulse |
| `observability-stack` | Prometheus · Grafana · Loki · Alertmanager · Pushgateway · webhook receiver → LogPulse |
| `access-control` | Auth-gated dashboard (FastAPI + Jinja2): Azure AD OAuth2 login, shows live mismatch counts + LogPulse history |
| `pulsegrid_common` | Shared Python library: LogPulse HTTP client, deduplication store |

---

## Tech stack

- **Python 3.12 / FastAPI** — all backend services
- **PostgreSQL** — separate database per service (CRM and ERP)
- **Azure AD / MSAL** — OAuth2 Authorization Code flow, signed session cookies (itsdangerous)
- **Prometheus · Grafana · Loki · Alertmanager** — full observability stack, provisioned via Docker Compose
- **Postman / Newman / GitHub Actions** — automated API health checks on a cron schedule
- **Docker / Docker Compose** — local development and service orchestration
- **LogPulse** — external AI-assisted RCA service (HTTP integration only)

---

## What this demonstrates

- **CRM/ERP integration with intentional fault injection** — the ~10% sync failure rate is by design, not a bug; reconciliation detects and reports it
- **AI-assisted Root Cause Analysis** — LogPulse classifies errors and returns structured triage results surfaced in the dashboard
- **Azure AD authentication** — real OAuth2 flow tested with a live Azure AD tenant; CSRF protection, signed session cookies, 8-hour TTL
- **Observability stack** — Prometheus alerting rules, Grafana dashboards (service health, error rates, reconciliation metrics), Loki log aggregation
- **Operational thinking** — deduplication logic prevents alert spam; graceful degradation when LogPulse is unavailable; health checks separate from business logic

---

*PulseGrid · Python · FastAPI · Azure AD · Prometheus/Grafana · PostgreSQL*

# PulseGrid — Agent-Harness Project Definition

*Format: pre-build spec for agent-driven, spec-based development. Use this as the baseline
context document for any AI coding harness (Cursor, Claude Code, Copilot Workspace, etc.)
before starting Phase 0.*

---

**1. TITLE:** PulseGrid

**2. ONE-LINE DESCRIPTION:** A CRM-ERP platform that detects real data mismatches, integration failures, and system errors, and feeds them via API into an existing AI RCA/ticketing system (LogPulse) — built as a personal portfolio project for an Application Support Engineer / Functioneel Beheerder targeting roles in the Netherlands.

**3. MATURITY LEVEL:** 1 — I chat with an AI agent, no automation. (No agent loop set up yet; this brief is the pre-work before starting.)

**4. STACK:**
- Language: Python 3.11+
- Backend framework: FastAPI (for CRM service, ERP service, and the observability webhook receiver)
- Database: PostgreSQL (one instance per service — separate DBs for CRM and ERP, not shared schema)
- API testing: Postman + Newman CLI
- Observability: Prometheus, Grafana, Loki, Alertmanager
- Auth: Microsoft Graph API + Azure AD (OAuth2 Authorization Code flow, MSAL library)
- Infra: Docker + Docker Compose (local dev, no orchestration platform like K8s planned for v1)
- CI: GitHub Actions (for scheduled API health checks)
- External dependency: LogPulse, a separate already-deployed FastAPI service on Railway (`https://log-pulse.up.railway.app`) — PulseGrid calls it via HTTP, does not modify it

**5. GREENFIELD OR EXISTING:** Greenfield — new repo, nothing built yet. (LogPulse is a separate, already-existing, already-deployed project by the same author; PulseGrid will integrate with it but is its own repo.)

**6. EDITOR/TOOL:** Uncertain — not yet decided between Cursor and VS Code + Claude Code.

**7. ARCHITECTURE SHAPE:** Modular monolith of independent services, not a single monolith and not full microservices with a message bus. Key components:
- `crm-service` — customers, orders, tickets
- `erp-service` — invoices, inventory, accounts
- `integration-sync` — logic inside crm-service that calls erp-service on order creation (not a standalone service)
- `reconciliation-job` — standalone scheduled script, reads both DBs directly
- `api-health-monitor` — Postman/Newman + GitHub Actions, not a running service
- `observability-stack` — Prometheus/Grafana/Loki/Alertmanager + a small webhook receiver service
- `access-control` — thin auth-gated dashboard service
- `pulsegrid_common` — shared library (just the LogPulse HTTP client), imported by reconciliation-job, api-health-monitor's report script, and the webhook receiver

**8. BUSINESS LOGIC NOT IN CODE:**
- The CRM→ERP sync must intentionally fail silently ~10% of the time (feature-flagged random chance) — this is a deliberate design choice to give the reconciliation job something real to catch. This is NOT a bug; an agent must not "fix" it by making sync 100% reliable, or the reconciliation module has nothing to detect.
- Severity mapping is not yet defined: what counts as `low` vs `high` vs `critical` when reporting to LogPulse is currently uncertain and needs to be decided before Phase 4/5 — not inferable from code.
- LogPulse's real API contract (endpoint path, payload shape, auth header) is NOT yet confirmed — the fallback build brief has a placeholder/fallback contract. This must be verified against LogPulse's live `/docs` before the integration is built for real; an agent should not assume the fallback is correct.
- No pricing, billing, or multi-tenant logic exists — this is explicitly out of scope, not an oversight.
- Duplicate-customer detection rule (same email, different id) is the only dedup rule defined — no fuzzy-matching or near-duplicate logic is intended for v1.
- Access control is a single-tenant login gate only — no role-based permissions are defined or wanted yet.

**9. SPECS STATUS:** Have a full build brief already (7 modules, phased build order, acceptance criteria per phase, folder structure, `.env` template). Priority order, from the existing spec:
1. CRM service
2. ERP service
3. CRM↔ERP integration (with intentional ~10% failure rate)
4. Reconciliation job → LogPulse (MVP milestone: full chain demoable here)
5. API health monitor → LogPulse
6. Observability stack → LogPulse
7. Access control (Azure AD)

**10. GIT/WORKFLOW DISCIPLINE:** Uncertain — not yet decided. No branch/commit convention chosen.

**11. TEAM SIZE:** Solo now. No stated intention to go multi-agent later — uncertain, not decided.

**12. CONSTRAINTS:**
- Time: informal target of ~35–45 hours total, roughly 3–4 weekends, driven by active NL job search timeline — no hard deadline stated.
- Banned tech: none explicitly banned, but message queues (Kafka/RabbitMQ), Kubernetes, and multi-tenant auth are explicitly excluded from v1 scope by design, not by prohibition.
- Compliance/regulatory: none — this is a portfolio/demo project using synthetic seed data, not real customer or business data.
- Budget: uncertain — Azure AD app registration, LLM API calls (via LogPulse, already built), and Railway/hosting costs not yet budgeted or confirmed as free-tier-feasible.

---

*Companion document: `PulseGrid-AI-Build-Brief.md` (module-by-module technical spec, repo structure, acceptance criteria per phase).*

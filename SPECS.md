# PulseGrid — Build Specs

## Phase order (dependency-driven, do not reorder)

- [x] Phase 1: CRM service
- [x] Phase 2: ERP service
- [x] Phase 3: CRM↔ERP integration (~10% intentional failure rate)
- [x] Phase 4: Reconciliation job → LogPulse (MVP demo milestone)
- [x] Phase 5: API health monitor → LogPulse
- [x] Phase 6: Observability stack → LogPulse
- [x] Phase 7: Access control (Azure AD)

## Phase 1: CRM service — checklist

- [x] Project scaffold (FastAPI app, folder structure, uv env)
- [x] DB schema: customers, orders, tickets
- [x] CRUD endpoints: customers
- [x] CRUD endpoints: orders
- [x] CRUD endpoints: tickets
- [x] Duplicate-customer detection (same email, different id)
- [x] Basic tests (Postman/Newman)
- [x] Seed script (synthetic data)

## Phase 2: ERP service — checklist

- [x] Project scaffold (FastAPI app, folder structure, uv env)
- [x] DB schema: invoices, inventory, accounts (migration 0002)
- [x] CRUD endpoints: invoices
- [x] CRUD endpoints: inventory
- [x] CRUD endpoints: accounts
- [x] Basic tests (Postman/Newman) — 44/44 assertions passed (25 requests)
- [x] Seed script (synthetic data)
- N/A Duplicate-entity detection — invoices/inventory/accounts have no same-entity-different-id case; accounts already 1:1 constrained to crm_customer_id via soft reference (see business-logic.md)

## Phase 3: CRM↔ERP integration — checklist

- [x] integration-sync: order creation in crm-service triggers ERP account lookup/create + draft invoice creation; ~10% intentional silent failure rate via feature-flagged random gate (SYNC_FAILURE_RATE env var, default 0.10); order always returns 201 regardless of sync outcome
- [x] integration-sync: Postman/Newman tests — 136/136 assertions passed (130 requests); 40-iter loop: 40/40 orders 201, 35 sync hits, 5 sync misses (first miss at iter 10); postman/integration-sync.postman_collection.json

## Phase 4: Reconciliation job — checklist

- [x] reconciliation-job/run.py: reads CRM and ERP DBs directly (not via HTTP); detects orders with no matching ERP invoice (catches ~10% intentional sync gap); sequential LogPulse POSTs; 90s timeout; retry on 502/network only
- [x] reconciliation-job/dedup.py: SQLite sidecar dedup state (dedup_state.db); schema: order_id + last_reported_at; 24h cooldown (DEDUP_COOLDOWN_HOURS tunable); prevents LogPulse spam on repeated runs
- [x] reconciliation-job/logpulse_client.py: TriageResult defensive deserialization (unknown fields ignored, all nullable); retry logic; no concurrent calls
- [x] reconciliation-job/models.py: pre-existing shadow ORM models for CRMOrder and ERPInvoice (read-only)
- [x] docs updated: patterns.md (dedup storage + LogPulse client conventions), tech-debt-tracker.md (SQLite tradeoff + cooldown default), learnings.md (created, LogPulse quirks), blocked.md (both blockers resolved)

## Phase 5: API health monitor — checklist

- [x] pulsegrid_common/: shared library extracted — logpulse_client.py (TriageResult + post_to_logpulse, full contract compliance), dedup.py (generic dedup_key TEXT PRIMARY KEY, replaces order_id-specific schema)
- [x] reconciliation-job/run.py: updated imports to pull from pulsegrid_common; dedup key changed to f"order:{order_id}" (generic string key); pyproject.toml updated with pulsegrid-common path dependency
- [x] api-health-monitor/pulsegrid-health.postman_collection.json: covers /health (both services, body assertion), GET list on all 6 entity endpoints (customers, orders, tickets, invoices, inventory, accounts), POST with invalid payload (422 validation alive check per service)
- [x] api-health-monitor/report_failures.py: reads Newman JSON output; deduplicates via pulsegrid_common.DedupStore (key: "endpoint:{method}:{url}"); calls LogPulse only for new/cooldown-expired failures; real-error-phrasing log_text; same contract rules as Phase 4
- [x] .github/workflows/api-health-monitor.yml: cron */15 * * * * (agent-chosen default, tunable); Newman runs with continue-on-error:true; report_failures.py always runs after Newman; Newman report uploaded as artifact
- [x] docs updated: patterns.md (generic dedup, api-health-monitor pattern, schedule interval, ephemeral CI dedup), tech-debt-tracker.md (pulsegrid_common extraction, dedup generalisation, schedule default, ephemeral dedup), learnings.md (Newman quirks, GitHub Actions gotchas, pulsegrid_common pattern)

## Phase 6: Observability stack — checklist

- [x] crm-service/app/main.py + pyproject.toml: prometheus-fastapi-instrumentator added; /metrics endpoint exposed via lifespan hook
- [x] erp-service/app/main.py + pyproject.toml: same as crm-service; /metrics endpoint exposed
- [x] reconciliation-job/run.py: Pushgateway push added (best-effort); pushes reconciliation_run_total + reconciliation_mismatches_total after each run; PUSHGATEWAY_URL env var (optional, defaults to empty/skip); uses httpx PUT text/plain Prometheus exposition format
- [x] reconciliation-job/models.py: shadow ORM models for CRMOrder + ERPInvoice extracted from run.py into standalone models.py
- [x] observability-stack/docker-compose.yml: Prometheus, Alertmanager, Pushgateway, Loki, Promtail, Grafana, webhook-receiver; port map documented; build context at repo root so pulsegrid_common path dep resolves
- [x] observability-stack/prometheus/prometheus.yml: scrapes crm-service:8000, erp-service:8001, pushgateway:9091 (honor_labels), webhook-receiver:9094, prometheus self; evaluation/scrape interval 15s; alertmanager connection; rule_files → rules.yml
- [x] observability-stack/prometheus/rules.yml: ServiceDown (up==0 for 1m, critical), HighErrorRate (5xx>5% for 2m, warning), ReconciliationMismatchRateHigh (mismatches/total>20%, fires immediately, warning), ReconciliationJobSilent (absent or stale >2h, warning)
- [x] observability-stack/alertmanager/alertmanager.yml: routes all alerts to pulsegrid-webhook receiver; group_by alertname+job+instance; group_wait 30s; group_interval 5m; repeat_interval 4h; send_resolved false; no auth
- [x] observability-stack/loki/loki-config.yml: single-binary mode, TSDB schema v13, filesystem storage, inmemory ring, reject_old_samples 168h
- [x] observability-stack/promtail/promtail-config.yml: Docker socket discovery, filters to compose project, labels job+container, pushes to loki:3100
- [x] observability-stack/grafana/provisioning/datasources/datasources.yml: Prometheus (default, uid=prometheus) + Loki (uid=loki) auto-provisioned
- [x] observability-stack/grafana/provisioning/dashboards/dashboards.yml: provider config pointing to /etc/grafana/provisioning/dashboards
- [x] observability-stack/grafana/provisioning/dashboards/pulsegrid.json: 6 panels — Service Health (stat, up{} for crm/erp/webhook), Request Rate (timeseries), 5xx Error Rate % (timeseries, threshold 5%/10%), Reconciliation Orders vs Mismatches (timeseries from Pushgateway), Log Volume (Loki rate), Live Logs (Loki stream); 30s refresh; uid=pulsegrid-obs-v1
- [x] observability-stack/webhook-receiver/app/main.py: FastAPI; POST /webhook; parses Alertmanager payload; firing-only; dedup via pulsegrid_common.DedupStore (key: alert:{alertname}:{instance}); sequential LogPulse calls; 90s timeout (via pulsegrid_common); real-error log_text phrasing; dedup state updated only on confirmed 200; /metrics via prometheus-fastapi-instrumentator lifespan hook
- [x] observability-stack/webhook-receiver/Dockerfile: base ghcr.io/astral-sh/uv:python3.12-bookworm-slim; build context = repo root; copies pulsegrid_common + webhook-receiver; uv sync --no-dev; CMD port 9094
- [x] observability-stack/webhook-receiver/pyproject.toml: fastapi, uvicorn, httpx, pulsegrid-common path dep (../../pulsegrid_common)
- [x] docs/tech-debt-tracker.md: created (Phase 6 tradeoffs logged)
- [x] docs/learnings.md: created (Phase 6 findings logged)

## Phase 7: Access control — checklist

- [x] access-control/: FastAPI service scaffold (pyproject.toml, Dockerfile, .gitignore)
- [x] Azure AD OAuth2 Auth Code flow via MSAL ConfidentialClientApplication: /auth/login, /auth/callback, /auth/logout
- [x] CSRF protection: state parameter generated with secrets.token_urlsafe(16), stored in pre-auth session cookie, validated on callback
- [x] Session: itsdangerous URLSafeSerializer signed cookie (8 h TTL, cookie name pulsegrid_session); no Redis/DB session store
- [x] Login gate: unauthenticated requests to / redirected to /auth/login; auth check via get_session()+is_authenticated() inline in handler (not Depends — see learnings.md)
- [x] MSAL synchronous calls wrapped in asyncio.to_thread() to avoid blocking FastAPI event loop
- [x] Dashboard (auth-gated): reconciliation mismatch count (direct CRM+ERP DB read), LogPulse /history (graceful fallback on unavailable), CRM+ERP /health pings
- [x] Jinja2 HTML templates: login.html (Microsoft sign-in button, error banner), dashboard.html (3 sections: mismatches, health, LogPulse history)
- [x] .env.example: Phase 7 vars added (AAD_CLIENT_ID, AAD_CLIENT_SECRET, AAD_TENANT_ID, AAD_REDIRECT_URI, SESSION_SECRET_KEY, ACCESS_CONTROL_PORT)
- [x] Docker: Dockerfile (build context = repo root; copies pulsegrid_common); service entry in access-control/docker-compose.yml (own compose file per patterns.md convention; build context = repo root so pulsegrid_common path dep resolves)
- [x] /health endpoint (no auth): returns {"status": "ok"}; /metrics intentionally absent (UI service)
- [x] docs/patterns.md: Phase 7 section added (session mechanism, port 8002, MSAL pattern, auth-gated route pattern, dashboard content defaults, Azure AD handoff)
- [x] docs/tech-debt-tracker.md: Phase 7 section added (signed cookie tradeoff, MSAL sync, LogPulse /history availability, Azure AD external handoff)
- [x] docs/learnings.md: Phase 7 section added (MSAL sync, state CSRF, redirect_uri mismatch, signed vs encrypted cookies, id_token claims, FastAPI RedirectResponse from Depends limitation)

## Phase 8: Guest/Demo Mode — checklist

> Adds a public read-only demo path for recruiters/portfolio visitors. No real
> Azure AD login required. Real Azure AD flow is completely untouched.
> All views are server-rendered FastAPI + Jinja2 (no new frontend framework).
> All data is synthetic seed data only. Strictly read-only throughout.

- [x] **Step 1 — Guest auth + seed data**: Add `/demo-login` endpoint to access-control
  that issues a signed `pulsegrid_session` cookie identical in structure to the real
  Azure AD session (same `itsdangerous` serializer, same TTL, same cookie name) but
  skips the OAuth redirect entirely. Payload: `authenticated=True`, `name="Demo Guest"`,
  `email="demo@pulsegrid.dev"`, `is_guest=True`. Extend both CRM and ERP seed scripts
  with additional rows that guarantee visible sync failures in the demo: add ≥4 extra
  CRM orders with no matching ERP invoice (intentional ~10% gap already built-in, but
  seed data must make at least 3–4 mismatches deterministic for a reliable demo).
  Update `.env.example` with `DEMO_MODE_ENABLED` guard flag.

- [x] **Step 2 — Home dashboard shell + nav**: Add a guest-aware landing page
  (`/guest/` or extend existing `/` with a guest branch) that shows a top-level nav
  to all eight demo screens. Reuse/extend the existing `dashboard.html` shell.
  Guest banner ("Demo Mode — read-only") visible on every page. No create/edit/delete
  actions exposed anywhere in guest mode.

- [x] **Step 3 — Reconciliation log view**: Guest-accessible route (`/guest/reconciliation`)
  that lists all detected CRM↔ERP mismatches — orders present in CRM with no matching
  ERP invoice. Direct DB read (same pattern as `dashboard.py _get_mismatch_counts()`).
  Shows: CRM order ID, customer name, order date, sync status (synced / missing invoice).
  This is the core "proof" screen for recruiters.

- [ ] **Step 4 — CRM + ERP list views**: Six read-only list routes under `/guest/`:
  customer list, order list, ticket list (CRM); invoice list, inventory list, accounts list
  (ERP). Direct DB reads via shadow models (pattern: `access-control/app/models.py`).
  Table layout, no pagination required for demo-scale data.

- [ ] **Step 5 — Integration-sync log view**: Guest route (`/guest/sync-log`) that shows
  per-order sync status derived from the CRM orders ↔ ERP invoices join (Option B:
  no new sync_events table; sync outcome inferred at query time by comparing CRM order
  IDs against ERP invoice crm_order_id values). Columns: order ID, customer name, order
  date, ERP invoice ID (or "—"), sync status (Synced / Failed — ~10% rows). Makes the
  intentional failure rate visible.

- [ ] **Step 6 — API health results table**: Guest route (`/guest/api-health`) that reads
  the latest Newman JSON report artifact and renders a pass/fail table per test.
  Fallback: if no Newman report is available, show a static "last known status" notice.
  No LogPulse call from this view — display only.

- [ ] **Step 7 — Observability view**: Check whether Grafana's `allow_embedding` and
  `X-Frame-Options` permit iframe embedding before implementing. If Grafana allows
  embedding → render `/guest/observability` with an iframe. If not → link-out pattern
  (same as LogPulse link-out in commit 2eca110), no forced blank iframe.
  Document the outcome in `docs/learnings.md § Phase 8`.

- [ ] **Step 8 — LogPulse link-out**: Guest route (`/guest/logpulse`) that shows RCA
  results for detected mismatches. Reuse the existing LogPulse `/history` fetch pattern
  already built in `dashboard.py _get_logpulse_history()`. Link out to LogPulse for
  full triage detail (same link-out pattern as commit 2eca110). No new LogPulse client
  code — import from `pulsegrid_common`.

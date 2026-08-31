# PulseGrid — Agent-Harness Project Definition (v3 — updated after Phase 8)

*Format: baseline context document for any AI coding harness (Antigravity CLI + Claude Sonnet 4.6,
Cursor, Claude Code, etc.) — feed this to a fresh chat before resuming at Phase 9.*

---

**1. TITLE:** PulseGrid

**2. ONE-LINE DESCRIPTION:** A CRM-ERP platform that detects real data mismatches, integration
failures, and system errors, and feeds them via API into an existing AI RCA/ticketing system
(LogPulse) — personal portfolio project for Application Support Engineer / Functioneel Beheerder
roles in the Netherlands.

**3. MATURITY LEVEL:** 3 — manual loop, item by item (Tip 15 precursor). Not yet at Tip 17 (Ralph Loop / full automation). Fresh chat per checklist item,
manual approval on every item.

**4. STACK (updated — Tabler added):**
- Python 3.11+, FastAPI, PostgreSQL (separate DB per service), Docker/Docker Compose
- Postman + Newman for API testing
- Prometheus/Grafana/Loki/Alertmanager (Phase 6 — deployed)
- Microsoft Graph API + Azure AD, MSAL, OAuth2 Auth Code flow (Phase 7 — deployed)
- GitHub Actions CI (Phase 5 — deployed)
- Python env: **uv** (not poetry/venv)
- LogPulse: separate deployed FastAPI service on Railway, `https://log-pulse.up.railway.app`
- **Tabler v1.4.0 (pinned)** — open-source HTML/CSS component library, CDN-loaded, no build
  step, dark-mode-native (`data-bs-theme="dark"`). Used for all Phase 8 guest/demo UI
  (base.html sidebar shell, cards, tables, badges). Rationale: fits existing FastAPI+Jinja2
  no-frontend-framework constraint, avoids writing custom CSS per screen. `@tabler/icons-webfont`
  also pulled via CDN.

**5. GREENFIELD:** Yes. Repo: `yashsolanki27/pulsegrid` on GitHub. Local path:
`K:\ADVANCE WEB\motolava\pulsegrid`. Works across PowerShell + WSL (watch for `.venv`
cross-filesystem lock issues — restart resolves it).

**6. EDITOR/TOOL:** **Antigravity CLI + Claude Sonnet 4.6 (thinking)** — switched from
VS Code + OpenCode mid-project. Coordinator file is `AGENTS.md` (not `CLAUDE.md`).

**7. ARCHITECTURE SHAPE:** Modular monolith, 8 components:
- `crm-service` — customers, orders, tickets **[Phase 1 — DONE]**
- `erp-service` — invoices, inventory, accounts **[Phase 2 — DONE]**
- `integration-sync` — inside crm-service, calls erp-service on order creation **[Phase 3 — DONE]**
- `reconciliation-job` — standalone scheduled script, reads both DBs directly **[Phase 4 — DONE]**
- `api-health-monitor` — Postman/Newman + GitHub Actions, not a service **[Phase 5 — DONE]**
- `observability-stack` — Prometheus/Grafana/Loki/Alertmanager + webhook receiver **[Phase 6 — DONE]**
- `access-control` — auth-gated dashboard (real Azure AD) **[Phase 7 — DONE]**
- `access-control/guest` — public read-only demo mode, 8 screens, Tabler UI **[Phase 8 — DONE]**
- `pulsegrid_common` — shared LogPulse HTTP client, used by reconciliation-job,
  api-health-monitor, webhook receiver, and guest LogPulse view

**8. BUSINESS LOGIC — LOCKED DECISIONS (all resolved through Phase 8):**

- **CRM→ERP sync failure:** intentionally fails ~10% of time via `random.random() < 0.1`
  (env var `SYNC_FAILURE_RATE`, default 0.10), no seed, no gate. **DO NOT FIX** — this is the
  feature reconciliation-job exists to catch. Order creation always succeeds regardless of
  sync outcome (asymmetric by design). Failure is log-only (no DB flag, no alert/webhook) —
  reconciliation detects it by directly comparing CRM/ERP data (order with no matching invoice),
  not by reading a status field.
- **Account entity** = customer billing account, 1:1 soft-ref to `crm_customer_id`
  (int, indexed, no DB FK — same pattern as `crm_order_id` on Invoice). Fields: balance,
  credit_limit (Numeric(12,2), ≥0). No ledger/GL logic, no vendor concept.
- **Invoice.status** = 4-state enum: `draft → sent → paid → overdue`. Transition guard via
  `dict[InvoiceStatus, set[InvoiceStatus]]`, invalid transitions → HTTP 422. Terminal states
  (paid, overdue) map to empty set.
- **InventoryItem.quantity** = DB CHECK constraint `>= 0` (dual-layer: Pydantic `ge=0` +
  DB CHECK `ck_inventory_quantity_nonneg`), on top of Pydantic-only validation. Violations
  caught and surfaced as HTTP 422, not a raw 500.
- **Dup-detection:** CRM = same email, different id (customers only). ERP entities
  (invoices/inventory/accounts) = **N/A**, no identity-dedup case exists there (documented
  reasoning in business-logic.md).
- **Severity mapping (low/high/critical):** this is a **PulseGrid-internal-only** concept,
  NOT sent to LogPulse (LogPulse's `TriageRequest` only accepts `log_text` — no severity
  field exists in its real contract). If PulseGrid wants its own severity labels for internal
  reporting/dashboards, that's separate logic layered on top of LogPulse's response, not
  part of the LogPulse payload itself. Suggested internal mapping (not yet implemented):
  order-with-no-invoice → high; account missing for customer → critical; timestamp-only
  drift → low.
- **LogPulse's real contract — CONFIRMED via live Swagger test, not guessed:**
  - Endpoint: `POST https://log-pulse.up.railway.app/triage`
  - No auth header required (confirmed via live 200 response, no auth sent)
  - Request: `{"log_text": string, 1–20000 chars}` — nothing else
  - Response (`TriageResult`): `id, created_at, raw_text, extracted_error_line, category,
    root_cause_summary, confidence (0-100 int), suggested_action, unclassified_reason
    (null unless unclassified), sop_command (null unless classified)`
  - `category` is a **closed 5-value enum**, server-enforced — safe to switch on
  - **Confidence threshold ~70%** — `log_text` needs real error-keyword phrasing
    ("sync error", "integration failure", "mismatch detected") or it returns
    `category: unclassified`, low confidence, generic text scores badly
  - **NO rate limiting** on their end — PulseGrid must throttle itself, no bursts/concurrency
  - **NO idempotency/dedup** — identical `log_text` creates a new DB row every call.
    PulseGrid's reconciliation-job maintains its own dedup state
    (`order_id, last_reported_at`, cooldown window) to avoid spamming duplicate
    triage entries for the same unresolved mismatch on every scheduled run.
  - No request timeout SLA on their side; their own recommendation: client timeout ~90s
    (survives one multi-key LLM retry chain), retry only on 502/network errors,
    never retry 422/404 (deterministic failures)
  - Schema stable but **unversioned** (no `/v1` prefix, no changelog) — deserialize
    defensively: ignore unknown fields, treat all fields nullable-safe
  - `log_text` persisted forever as `raw_text`, exposed via `/history`, no TTL/retention/
    PII-scrubbing — fine since only synthetic seed data is used, but don't put realistic
    PII in test log_text regardless
- **No pricing/billing/multi-tenant logic** — out of scope, not an oversight.
- **Access control** = single-tenant login gate (Azure AD, Phase 7) + separate public
  read-only guest/demo path (Phase 8), no RBAC.
- **Guest/demo mode isolation (Phase 8):** guest sessions (`is_guest=True`) are strictly
  confined to `/guest/*` routes. Real dashboard (`/`) and all authenticated non-guest
  routes reject guest sessions and redirect to `/guest/`; unauthenticated requests to any
  `/guest/*` route redirect to `/auth/login`. This boundary was initially missing (see
  Phase 8 Regression note below) and has since been fixed and verified.
- **Guest data source:** demo-gap orders are seed-level fixed rows (deterministic, ≥4
  guaranteed CRM↔ERP mismatches), layered on top of the untouched random
  `SYNC_FAILURE_RATE` mechanism — both coexist without conflict.
- **Guest sync-log view:** derived at query time from the CRM order ↔ ERP invoice join
  (Option B) — no new `sync_events` table, consistent with reconciliation-job's existing
  direct-comparison pattern.
- **Guest observability view:** Grafana `GF_SECURITY_ALLOW_EMBEDDING` defaults false in
  this deployment (confirmed, not assumed) — link-out pattern used instead of iframe,
  same pattern as the LogPulse link-out.

**9. SPECS STATUS:**
1. ✅ CRM service — **complete** (scaffold, DB schema, CRUD, dup-detection, Postman/Newman
   57/57 assertions, seed script, verified live, pushed)
2. ✅ ERP service — **complete** (scaffold, DB schema w/ enum+CHECK, CRUD, dup-detection
   N/A, Postman/Newman 44/44 assertions, seed script audited+fixed for drift, pushed)
3. ✅ CRM↔ERP integration — **complete** (integration-sync with intentional ~10% failure,
   self-audited 5/5 clean against retry/alert/randomness/doc-note checks, Postman/Newman
   136/136 assertions across 40-iteration statistical test, pushed)
4. ✅ Reconciliation job → LogPulse — **complete** (mismatch detection, own dedup state,
   real-error-phrasing log_text construction, sequential POSTs, 90s timeout w/ selective
   retry, defensive deserialization)
5. ✅ API health monitor → LogPulse — **complete**
6. ✅ Observability stack → LogPulse — **complete**
7. ✅ Access control (Azure AD) — **complete**
8. ✅ Guest/demo mode — **complete**, 8/8 steps:
   1. Guest auth + seed data (`/demo-login`, signed session cookie, demo-gap seed rows)
   2. Home dashboard shell + nav (Tabler base.html, guest banner, 8-screen nav)
   3. Reconciliation log view (`/guest/reconciliation`)
   4. CRM + ERP list views — 6 routes (customers, orders, tickets, invoices, inventory, accounts)
   5. Integration-sync log view (`/guest/sync-log`, Option B derived join)
   6. API health results table (`/guest/api-health`, Newman JSON reader + fallback)
   7. Observability view (`/guest/observability`, link-out — Grafana embedding confirmed blocked)
   8. LogPulse link-out (`/guest/logpulse`, reuses existing `pulsegrid_common` history fetch)

   **Phase 8 regression cycle (post-completion, full QA pass):**
   - Suites 1–3 (CRM/ERP/integration-sync Postman/Newman): all pass vs baseline
     (1 probabilistic assertion flake explained, not a bug — P≈1.48% no-sync-hit-in-40-runs)
   - Azure AD flow (Phase 7): unaffected, verified end-to-end
   - Guest write-safety: all 12 guest endpoints reject POST/PUT/PATCH/DELETE (405)
   - **Bug found + fixed:** guest session boundary gap — `is_guest` was never enforced
     (docstring said it should be, code only checked `is_authenticated`). Guest sessions
     could reach the real `/` dashboard. Fixed both directions: real routes now reject
     guests, guest routes now reject non-guest sessions. Logged in
     `docs/learnings.md § Phase 8 Regression`.
   - Fresh-seed load test: all 12 guest routes 200 OK, zero 500s
   - Final verdict: **clean**

Not started — Phase 9 (TracePulse), scope TBD.

**10. GIT/WORKFLOW DISCIPLINE (established, keep using):**
- Coordinator file: `AGENTS.md`
- One commit per finished checklist item (not per module)
- `blocked.md` trigger: undefined business/domain decision not inferable from docs → stop,
  write it, wait for human. Technical errors → agent self-fixes first, escalates if stuck.
- Every prompt ends with a mandatory short summary format (files changed, key decisions,
  edge cases, blocked.md flags, scope-match confirmation) — no full code dumps unless asked.
- Post-approval template: *"Approved. Tick '<item>' in SPECS.md, then commit and push
  following the one-item-per-commit rule."*
- Fresh chat per checklist item for real build work; same-chat is fine only for trivial
  one-line doc edits with no decision-making surface area.
- Docs split by concern: `architecture.md`, `stack.md`, `business-logic.md`, `patterns.md`,
  `docs/learnings.md`
- Full regression/QA pass run after Phase 8 completion (Tip 21 cycle review) — establishes
  the pattern to repeat after future phases.

**11. TEAM SIZE:** Solo. No multi-agent plans.

**12. CONSTRAINTS:** ~35–45 hrs total, 3-4 weekends, NL job-search driven. No Kafka/K8s/
multi-tenant auth in v1. No compliance concerns (synthetic data only). Budget for Azure AD /
Railway hosting still unconfirmed as free-tier-feasible.

---
*Phase 9 (TracePulse) planning not yet started — kept as a separate discussion once this
doc is confirmed accurate.*

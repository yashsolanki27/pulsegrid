# PulseGrid — Agent-Harness Project Definition (v2 — updated after Phases 1-3)

*Format: baseline context document for any AI coding harness (Antigravity CLI + Claude Sonnet 4.6,
Cursor, Claude Code, etc.) — feed this to a fresh chat before resuming at Phase 4.*

---

**1. TITLE:** PulseGrid

**2. ONE-LINE DESCRIPTION:** A CRM-ERP platform that detects real data mismatches, integration
failures, and system errors, and feeds them via API into an existing AI RCA/ticketing system
(LogPulse) — personal portfolio project for Application Support Engineer / Functioneel Beheerder
roles in the Netherlands.

**3. MATURITY LEVEL:** 3 — manual loop, item by item (Tip 15 precursor). Not yet at Tip 17 (Ralph Loop / full automation). Fresh chat per checklist item,
manual approval on every item.

**4. STACK (unchanged):**
- Python 3.11+, FastAPI, PostgreSQL (separate DB per service), Docker/Docker Compose
- Postman + Newman for API testing
- Prometheus/Grafana/Loki/Alertmanager (Phase 6, not yet built)
- Microsoft Graph API + Azure AD, MSAL, OAuth2 Auth Code flow (Phase 7, not yet built)
- GitHub Actions CI (Phase 5, not yet built)
- Python env: **uv** (not poetry/venv)
- LogPulse: separate deployed FastAPI service on Railway, `https://log-pulse.up.railway.app`

**5. GREENFIELD:** Yes. Repo: `yashsolanki27/pulsegrid` on GitHub. Local path:
`K:\ADVANCE WEB\motolava\pulsegrid`. Works across PowerShell + WSL (watch for `.venv`
cross-filesystem lock issues — restart resolves it).

**6. EDITOR/TOOL:** **Antigravity CLI + Claude Sonnet 4.6 (thinking)** — switched from
VS Code + OpenCode mid-project. Coordinator file is `AGENTS.md` (not `CLAUDE.md`).

**7. ARCHITECTURE SHAPE:** Modular monolith, 8 components:
- `crm-service` — customers, orders, tickets **[Phase 1 — DONE]**
- `erp-service` — invoices, inventory, accounts **[Phase 2 — DONE]**
- `integration-sync` — inside crm-service, calls erp-service on order creation **[Phase 3 — DONE]**
- `reconciliation-job` — standalone scheduled script, reads both DBs directly **[Phase 4 — NEXT]**
- `api-health-monitor` — Postman/Newman + GitHub Actions, not a service **[Phase 5]**
- `observability-stack` — Prometheus/Grafana/Loki/Alertmanager + webhook receiver **[Phase 6]**
- `access-control` — auth-gated dashboard **[Phase 7]**
- `pulsegrid_common` — shared LogPulse HTTP client, used by reconciliation-job,
  api-health-monitor, webhook receiver

**8. BUSINESS LOGIC — LOCKED DECISIONS (all resolved, nothing pending for Phases 1-4):**

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
    **PulseGrid's reconciliation-job MUST maintain its own dedup state**
    (e.g. `order_id, last_reported_at`, cooldown window) or it will spam duplicate
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
- **Access control** = single-tenant login gate only, no RBAC (Phase 7, not started).

**9. SPECS STATUS:**
1. ✅ CRM service — **complete** (scaffold, DB schema, CRUD, dup-detection, Postman/Newman
   57/57 assertions, seed script, verified live, pushed)
2. ✅ ERP service — **complete** (scaffold, DB schema w/ enum+CHECK, CRUD, dup-detection
   N/A, Postman/Newman 44/44 assertions, seed script audited+fixed for drift, pushed)
3. ✅ CRM↔ERP integration — **complete** (integration-sync with intentional ~10% failure,
   self-audited 5/5 clean against retry/alert/randomness/doc-note checks, Postman/Newman
   136/136 assertions across 40-iteration statistical test, pushed)
4. ⏳ Reconciliation job → LogPulse — **NEXT.** Must include: mismatch detection (order
   with no invoice), own dedup state, real-error-phrasing log_text construction, sequential
   (non-burst) POSTs to LogPulse, 90s timeout with selective retry, defensive deserialization.
5. Not started — API health monitor → LogPulse
6. Not started — Observability stack → LogPulse
7. Not started — Access control (Azure AD)

**10. GIT/WORKFLOW DISCIPLINE (established, keep using):**
- Coordinator file: `AGENTS.md`
- One commit per finished checklist item (not per module)
- `blocked.md` trigger: undefined business/domain decision not inferable from docs → stop,
  write it, wait for human. Technical errors → agent self-fixes first, escalates if stuck.
- Every prompt ends with: *"When showing results, summarize only (file list, key decisions,
  edge cases, blocked.md flags, approval-match confirmation) — no full code dumps unless asked."*
- Post-approval template: *"Approved. Tick '<item>' in SPECS.md, then commit and push
  following the one-item-per-commit rule. Show me git output."*
- Fresh chat per checklist item for real build work; same-chat is fine only for trivial
  one-line doc edits with no decision-making surface area.
- Docs split by concern: `architecture.md`, `stack.md`, `business-logic.md`, `patterns.md`

**11. TEAM SIZE:** Solo. No multi-agent plans.

**12. CONSTRAINTS:** ~35–45 hrs total, 3-4 weekends, NL job-search driven. No Kafka/K8s/
multi-tenant auth in v1. No compliance concerns (synthetic data only). Budget for Azure AD /
Railway hosting still unconfirmed as free-tier-feasible.

---
*Companion file `PulseGrid-AI-Build-Brief.md` referenced but not yet uploaded to any chat —
if it exists locally, feed it alongside this doc for Phase 4+ field-level schema detail.*

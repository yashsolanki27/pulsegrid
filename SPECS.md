# PulseGrid — Build Specs

## Phase order (dependency-driven, do not reorder)

- [ ] Phase 1: CRM service
- [x] Phase 2: ERP service
- [ ] Phase 3: CRM↔ERP integration (~10% intentional failure rate)
- [x] Phase 4: Reconciliation job → LogPulse (MVP demo milestone)
- [ ] Phase 5: API health monitor → LogPulse
- [ ] Phase 6: Observability stack → LogPulse
- [ ] Phase 7: Access control (Azure AD)

## Phase 1: CRM service — checklist

- [x] Project scaffold (FastAPI app, folder structure, uv env)
- [x] DB schema: customers, orders, tickets
- [x] CRUD endpoints: customers
- [x] CRUD endpoints: orders
- [x] CRUD endpoints: tickets
- [x] Duplicate-customer detection (same email, different id)
- [x] Basic tests (Postman/Newman)
- [ ] Seed script (synthetic data)

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

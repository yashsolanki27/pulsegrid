# PulseGrid — Build Specs

## Phase order (dependency-driven, do not reorder)

- [ ] Phase 1: CRM service
- [x] Phase 2: ERP service
- [ ] Phase 3: CRM↔ERP integration (~10% intentional failure rate)
- [ ] Phase 4: Reconciliation job → LogPulse (MVP demo milestone)
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

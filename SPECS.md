# PulseGrid — Build Specs

## Phase order (dependency-driven, do not reorder)

- [ ] Phase 1: CRM service
- [ ] Phase 2: ERP service
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

- [x] Project scaffold (FastAPI app, folder structure, uv env) — invoices + inventory only; accounts BLOCKED (see blocked.md)
- [ ] DB schema: accounts (BLOCKED — entity purpose undefined, see blocked.md)
- [ ] CRUD endpoints: invoices
- [ ] CRUD endpoints: inventory
- [ ] CRUD endpoints: accounts (BLOCKED — depends on schema)
- [ ] Basic tests (Postman/Newman)
- [ ] Seed script (synthetic data)

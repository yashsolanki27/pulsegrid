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

- [ ] Project scaffold (FastAPI app, folder structure, uv env)
- [ ] DB schema: customers, orders, tickets
- [ ] CRUD endpoints: customers
- [ ] CRUD endpoints: orders
- [ ] CRUD endpoints: tickets
- [ ] Duplicate-customer detection (same email, different id)
- [ ] Basic tests (Postman/Newman)
- [ ] Seed script (synthetic data)

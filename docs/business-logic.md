# Business Logic — Not Inferable From Code

- CRM→ERP sync fails ~10% of time, feature-flagged, INTENTIONAL. Do not fix.

## CRM→ERP sync failure injection ⚠️ DO NOT "FIX" ⚠️

**This is not a bug. Do not remove, retry around, or reduce this failure rate.**

On every order creation the integration-sync module (`crm-service/app/sync.py`)
runs a coin-flip before making any HTTP call:

```python
# crm-service/app/sync.py — _should_fail_this_sync()
return random.random() < _SYNC_FAILURE_RATE   # default 0.10 = 10 %
```

- If the coin-flip fires (~10 % of calls): sync is **silently skipped** — a
  WARNING is logged, no HTTP call is made, no exception is raised.
- The order creation endpoint returns **HTTP 201 in all cases** — sync outcome
  never blocks or alters the CRM response.
- The `SYNC_FAILURE_RATE` env var controls the probability (default `0.10`).
  Setting it to `0` in production violates the Phase 4 design contract.

**Why this exists:** The reconciliation-job (Phase 4) needs real gaps between
CRM orders and ERP invoices to have meaningful data to catch and report.
Making sync 100 % reliable would leave the reconciliation-job nothing to do,
which defeats the demo milestone. The ~10 % gap is the feature, not the fault.
- Severity mapping (low/high/critical) for LogPulse reports: [UNRESOLVED — see blocked.md]
- LogPulse API contract (endpoint, payload, auth header): [UNRESOLVED — verify against
  live /docs before Phase 4/5, see blocked.md]
- No pricing/billing/multi-tenant logic — explicitly out of scope, not missing.
- Dedup rule: same email + different id = duplicate. No fuzzy matching in v1.
- Dup-detection N/A for ERP entities (invoices, inventory, accounts): no same-entity-different-id case exists; accounts are already 1:1 constrained to crm_customer_id via soft reference (one account per CRM customer by convention).
- Access control: single-tenant login gate only. No RBAC.

## Account entity (ERP)

- Account = customer billing account, 1:1 with CRM customer.
- Fields: `crm_customer_id` (soft ref, int, indexed, no DB FK), `balance`, `credit_limit`.
- `balance` and `credit_limit` are `Numeric(12, 2)`, non-negative (Pydantic `ge=0`).
- No overdraft logic or payment processing in v1.

## Invoice status lifecycle

- Allowed statuses: `draft`, `sent`, `paid`, `overdue`.
- Initial status on creation: `draft`.
- Valid transitions (enforced at service layer, not DB):
  - `draft → sent`
  - `sent → paid`
  - `sent → overdue`
- No skipping states (e.g. `draft → paid` is INVALID).
- No reverse transitions (e.g. `paid → draft` is INVALID).
- `paid` and `overdue` are terminal states — no further transitions allowed.

## Inventory quantity constraint

- `quantity` must be >= 0 at all times (no backorder / negative-stock in v1).
- Enforced at two layers: Pydantic `ge=0` (API layer) + DB CHECK constraint
  (`ck_inventory_quantity_nonneg`). DB violation returns HTTP 422 (not 500).
- Note: the qty>0 seed choice (commit 17b2700) was not user-specified — it's a reasonable agent decision to represent actively-stocked demo data, not a documented business rule. CHECK constraint itself still permits 0.

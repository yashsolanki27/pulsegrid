# Business Logic — Not Inferable From Code

- CRM→ERP sync fails ~10% of time, feature-flagged, INTENTIONAL. Do not fix.
- Severity mapping (low/high/critical) for LogPulse reports: [UNRESOLVED — see blocked.md]
- LogPulse API contract (endpoint, payload, auth header): [UNRESOLVED — verify against
  live /docs before Phase 4/5, see blocked.md]
- No pricing/billing/multi-tenant logic — explicitly out of scope, not missing.
- Dedup rule: same email + different id = duplicate. No fuzzy matching in v1.
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

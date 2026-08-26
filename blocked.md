BLOCKED: Severity mapping (low/high/critical) not yet defined. Needed before Phase 4.
BLOCKED: LogPulse real API contract not confirmed. Needed before Phase 4/5.
BLOCKED: [erp-service] Account entity schema undefined. "accounts" in the ERP context
  is not described in any doc (financial ledger account? vendor account? other?).
  Cannot implement Account model, schemas, or CRUD router until purpose and fields
  are defined. Needed before Phase 2 accounts work can proceed.
BLOCKED: [erp-service] Invoice status allowed values and transition rules not defined.
  Status stored as plain String("pending" default) in v1 scaffold; no enum or
  transition guard implemented. Must define allowed statuses before Phase 3
  integration-sync writes to this field.
BLOCKED: [erp-service] Inventory quantity constraint policy not defined. Whether
  quantity may go negative (backorder / negative-stock) is a business rule not
  documented anywhere. Schema defaults to ge=0 at API layer only; DB has no CHECK
  constraint. Must resolve before any stock-deduction logic is built.

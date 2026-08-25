# Business Logic — Not Inferable From Code

- CRM→ERP sync fails ~10% of time, feature-flagged, INTENTIONAL. Do not fix.
- Severity mapping (low/high/critical) for LogPulse reports: [UNRESOLVED — see blocked.md]
- LogPulse API contract (endpoint, payload, auth header): [UNRESOLVED — verify against
  live /docs before Phase 4/5, see blocked.md]
- No pricing/billing/multi-tenant logic — explicitly out of scope, not missing.
- Dedup rule: same email + different id = duplicate. No fuzzy matching in v1.
- Access control: single-tenant login gate only. No RBAC.

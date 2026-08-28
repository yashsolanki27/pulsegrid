# Coding Patterns

## Service structure

Each service mirrors the same layout:
```
<service>/
  app/
    __init__.py
    db.py          # engine + SessionLocal + get_db()
    main.py        # FastAPI app, router includes, /health
    models.py      # SQLAlchemy DeclarativeBase + ORM models
    schemas.py     # Pydantic Create/Update/Out schemas
    routers/
      __init__.py
      <entity>.py  # one file per entity, CRUD pattern
  migrations/
    env.py         # reads <SERVICE>_DATABASE_URL env var
    script.py.mako
    versions/
      0001_initial.py
  tests/
    __init__.py
  alembic.ini
  Dockerfile
  docker-compose.yml  # scope depends on service type — see convention below
  pyproject.toml
  uv.lock
  .gitignore
```

## Docker Compose file convention (per-service)

Each service has its own `docker-compose.yml` at its service root. Scope varies by service type:

- **crm-service**, **erp-service**: DB-only compose (Postgres container). The app itself
  runs via `uv run uvicorn ...` locally; no app service entry in compose.
- **access-control**: No DB of its own. The compose file contains the app service entry
  (commented out, pending Azure AD app registration). Build context must be the repo root
  to resolve the `pulsegrid_common` path dependency.
- **observability-stack**: Contains all observability services (Prometheus, Grafana, Loki,
  Alertmanager, Pushgateway, Promtail, webhook-receiver) in one compose file.
  No other service's entries belong here.

**Convention:** A service's compose file only contains services owned by that service.
Cross-service entries (e.g. access-control inside observability-stack) are structurally wrong
and must not appear.

## DB URL environment variable convention

- CRM service: `CRM_DATABASE_URL` (default: postgresql+psycopg://postgres:postgres@localhost:5432/crm)
- ERP service: `ERP_DATABASE_URL` (default: postgresql+psycopg://postgres:postgres@localhost:5433/erp)

## Port conventions (local dev)

- CRM Postgres: 5432
- ERP Postgres: 5433 (host) → 5432 (container)
- CRM app: 8000
- ERP app: 8001

## Router pattern

- `_get_<entity>_or_404(db, id)` helper for reuse
- POST → 201, GET list ordered by id, PATCH → exclude_unset, DELETE → 204
- IntegrityError on delete → 409 with detail
- No response body on DELETE (returns Response(status_code=204))

## Cross-DB references

- CRM↔ERP cross-service references (e.g. Invoice.crm_order_id, Account.crm_customer_id)
  are soft references: no SQLAlchemy FK constraint, no DB-level constraint. Referential
  integrity is the responsibility of the calling service (integration-sync).
- Pattern: plain `Integer()` column, `index=True`, no `ForeignKey(...)`.

## Status enum + transition guard pattern

When an entity has a lifecycle with ordered states:
1. Define a Python `str, enum.Enum` in `models.py` (e.g. `InvoiceStatus`).
2. Use SQLAlchemy `Enum(MyEnum, name="myenum")` so Postgres gets a native enum type.
3. Declare the transition DAG as a `dict[Status, set[Status]]` constant at the top
   of the router module (e.g. `_ALLOWED_TRANSITIONS`).
4. Call a `_assert_valid_transition(current, next)` helper before committing;
   raise HTTP 422 on invalid transitions with a message listing allowed next states.
5. Terminal states map to `set()` — attempting any transition from them returns 422.
6. The schema's `Update` model accepts `status: MyEnum | None` so invalid *values*
   are caught by Pydantic before the transition guard even runs.

**Invoice transitions (established):**
`draft → sent → paid` or `draft → sent → overdue`. No skipping, no reversal.

## DB CHECK constraints + app-layer handling

When a field must be non-negative (or satisfy any invariant) at the DB level:
1. Add `CheckConstraint("col >= 0", name="ck_<table>_<col>_<rule>")` to
   `__table_args__` in the model.
2. Add the same constraint in the Alembic migration via `op.create_check_constraint(...)`.
3. In the router, replace bare `db.commit()` with a helper that catches
   `IntegrityError`, checks `exc.orig` for the constraint name, and raises
   HTTP 422 with a human-readable message. Re-raise any unrelated IntegrityErrors.
4. This dual-layer defence (Pydantic `ge=0` + DB CHECK) ensures that code paths
   that bypass the API schema (e.g. direct SQL, future stock-deduction logic)
   still return a handled error, not a 500.

**Constraint name convention:** `ck_<tablename>_<column>_<rule>` (e.g. `ck_inventory_quantity_nonneg`).

## Docker image

- Base: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`
- CMD: `uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port <port>`

## Seed script pattern

Each service has `scripts/seed.py`, run via `uv run python -m scripts.seed`.

**Conventions (both services mirror this pattern):**
- Run-once by default: refuses to execute if primary table already has rows.
- `--force` flag: wipes all seeded tables in dependency order, then reseeds.
- Data constants defined as module-level tuples at the top of the file.
- Uses `SessionLocal()` directly (not `get_db()` generator — script context).
- `db.flush()` after inserts that produce IDs needed for subsequent rows.
- Single `db.commit()` at end (atomic seed).
- Print summary of seeded row counts on success.

**Lifecycle entities (e.g. Invoice):**
- Do not set terminal status directly — insert as the valid initial state
  (`draft`) and replay each transition using `_assert_valid_transition` from
  the router module. This proves the fixture data follows the transition DAG.
- Example: `draft → sent → paid` is written as two explicit calls to the guard,
  then `inv.status = next_status` for each step.

**Cross-DB soft references (e.g. `crm_customer_id`, `crm_order_id`):**
- Use integer IDs that match the other service's seed data (e.g. 1–5 for the
  first five CRM customers). Document the assumption in the script's docstring.
- These are safe placeholder ints even if the other service is not running —
  no DB-level FK constraint is enforced.

**Inventory / non-negative constraint:**
- Seed data uses strictly positive quantities (> 0); quantity=0 is valid at
  runtime but intentionally avoided in fixtures to represent active stock.

## Dedup state storage (generic — pulsegrid_common)

All LogPulse callers (reconciliation-job, api-health-monitor, webhook receiver) need
their own dedup state to prevent re-reporting the same failure on every scheduled run
(LogPulse has no idempotency).

**Chosen storage: SQLite sidecar file** (path via env var per caller).
- Schema: `dedup_state(dedup_key TEXT PRIMARY KEY, last_reported_at TEXT)`.
- Key is a generic string — callers namespace their own keys:
  - reconciliation-job: `"order:{order_id}"`
  - api-health-monitor: `"endpoint:{method}:{url_without_query}"`
- Rationale: jobs have no Postgres DB of their own; a lightweight SQLite file avoids
  a third Postgres instance. Portable, survives restarts, works in Docker via a mounted
  volume. Single-writer workload — SQLite sufficient.
- Alternative considered: Postgres table in CRM or ERP DB — rejected to keep concerns
  separated and avoid cross-DB coupling from the job's state into the service DBs.
- Cooldown window: 24 hours (`DEDUP_COOLDOWN_HOURS` env var, default 24). Tunable —
  not a business rule. See tech-debt-tracker.md for the tradeoff note.

**Dedup reuse decision (Phase 5 refactor):**
The original reconciliation-job used `order_id INTEGER PRIMARY KEY`. Phase 5 required
the same mechanism for api-health-monitor with endpoint-based keys. Rather than
duplicating the module, the schema was generalised to `dedup_key TEXT PRIMARY KEY`
and the module extracted into `pulsegrid_common`. This keeps a single implementation
with zero duplication while remaining backward-compatible (reconciliation-job just
wraps its keys as `f"order:{order_id}"`). See tech-debt-tracker.md for the SQLite
sidecar tradeoff note (still applies to all callers).

## LogPulse client conventions (pulsegrid_common)

The LogPulse HTTP client lives in `pulsegrid_common/logpulse_client.py` and is
imported by all callers. **Do not duplicate it locally.**

- Timeout: 90 s (httpx `timeout=90.0`).
- Retry: one retry on 502 / network-level errors (`ConnectError`, `RemoteProtocolError`,
  `TimeoutException`). Never retry 422/404 — deterministic failures.
- Concurrency: sequential only; caller must never invoke concurrently (LogPulse has no
  rate limiting — burst protection is PulseGrid's responsibility).
- Deserialization: `TriageResult.from_dict()` filters to known fields only; all fields
  nullable-safe. Unknown fields from future LogPulse schema changes are silently ignored.
- Dedup update: only mark key as reported after a confirmed 200 response.
  Failed calls leave dedup state unchanged so the next run retries.

## api-health-monitor pattern

- **Not a service.** Postman/Newman + GitHub Actions only. No running process.
- Collection: `api-health-monitor/pulsegrid-health.postman_collection.json`
  - Uses collection variables `{{crm_base_url}}` / `{{erp_base_url}}` (overridden via
    Newman `--env-var` in the GitHub Actions step; defaults to localhost for local use).
  - Coverage: `/health` (liveness + body assertion), GET list on all 6 entity endpoints,
    one POST with invalid payload per service (422 validation alive check).
- Newman runs with `--reporters cli,json` and exports `newman-report.json`.
- `report_failures.py` reads the JSON output and calls LogPulse for failures.
  Always runs after Newman (Newman step has `continue-on-error: true`).
- `log_text` phrasing pattern:
  `"API health check failed: {METHOD} {url} returned {status}, integration failure detected. Test: \"{name}\". Assertion errors: {errors}"`
  Keywords "API health check failed" and "integration failure detected" hit the ~70% confidence threshold.
- GitHub Actions secrets: `CRM_BASE_URL`, `ERP_BASE_URL`. Optional: `LOGPULSE_URL`,
  `DEDUP_COOLDOWN_HOURS` (as a variable, not a secret).

## GitHub Actions schedule interval (api-health-monitor)

Default cron: `*/15 * * * *` (every 15 minutes). Agent-chosen — not specified in
business-logic.md or user input. This is a tunable, not a business rule.
Override by editing the `cron:` field in `.github/workflows/api-health-monitor.yml`
without any code change. Considerations for tuning:
- More frequent → faster detection, more LogPulse calls (dedup prevents spam within cooldown).
- Less frequent → quieter, slower detection. Minimum sensible interval for a demo: 15 min.
- If cooldown (`DEDUP_COOLDOWN_HOURS`) is shorter than the cron interval, the dedup has
  no effect — keep cooldown >= cron interval (24h default vs 15min cron: fine).

## Dedup persistence in CI (GitHub Actions)

The SQLite dedup sidecar (`health_dedup_state.db`) is persisted across GitHub Actions
runs using `actions/cache` with the **fixed** key `api-health-monitor-dedup-v1`.

Key design decisions:
- Key is stable across runs (not per-run-id, not per-commit) — same entry is reused
  every execution so cooldown state accumulates correctly.
- `actions/cache/restore` runs **before** Newman so the store is populated at report time.
- `actions/cache/save` runs **after** `report_failures.py` with `if: always()` — a
  failed run still persists any dedup updates made before the failure.
- `DEDUP_DB_PATH=health_dedup_state.db` is explicitly set in the workflow env so the
  file path matches the cache path.
- GitHub cache automatically overwrites an entry with the same key on save — no
  accumulating stale entries.

The 24h cooldown window therefore spans across workflow executions as intended: a
broken endpoint is reported once, then suppressed for 24h regardless of how many
15-minute runs fire in that window. Dedup key scheme unchanged:
`endpoint:{method}:{url_without_query}`.

## Prometheus /metrics exposure pattern (all FastAPI services)

All FastAPI services (crm-service, erp-service, webhook-receiver) expose `/metrics`
using `prometheus-fastapi-instrumentator`.

**crm-service and erp-service** use module-level initialisation (no lifespan required):

```python
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="<service-name>")
# instrument() adds middleware; expose() adds the /metrics route.
# Both are safe at module level — called once before the app starts serving.
Instrumentator().instrument(app).expose(app)
```

**webhook-receiver** wraps in a lifespan hook (it has other lifespan setup):

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

@asynccontextmanager
async def lifespan(app: FastAPI):
    Instrumentator().instrument(app).expose(app)
    yield

app = FastAPI(title="<service-name>", lifespan=lifespan)
```

Both approaches are functionally equivalent — `prometheus-fastapi-instrumentator`
supports either. Use whichever fits the service's existing structure.

Add `prometheus-fastapi-instrumentator>=6.1` to `pyproject.toml` dependencies.
Prometheus scrapes `/metrics` (default path). No auth on the endpoint.

## Alertmanager → webhook-receiver → LogPulse chain

Firing alerts flow: Prometheus → Alertmanager → `POST /webhook` on webhook-receiver →
`pulsegrid_common.post_to_logpulse()` → LogPulse.

Rules:
- Only `"firing"` alerts are forwarded; `"resolved"` are logged and discarded.
- Dedup key: `"alert:{alertname}:{instance}"` (24h cooldown, same pattern as other callers).
- Sequential LogPulse calls only (no concurrency).
- 90s timeout, one retry on 502/network (via pulsegrid_common — same contract as Phase 4/5).
- Dedup state updated only on confirmed 200 from LogPulse.
- `log_text` phrasing: `"PulseGrid alert firing: {alertname} on {instance} ... Integration failure detected"` — keywords hit ~70% LogPulse confidence threshold.

## Pushgateway metrics push pattern (reconciliation-job)

One-shot scripts that cannot be scraped directly push metrics via Pushgateway.
reconciliation-job uses raw httpx PUT + Prometheus text exposition format:

```python
body = (
    "# HELP reconciliation_run_total ...\n"
    "# TYPE reconciliation_run_total gauge\n"
    f"reconciliation_run_total {run_total}\n"
    ...
)
httpx.put(f"{PUSHGATEWAY_URL}/metrics/job/reconciliation-job", content=body,
          headers={"Content-Type": "text/plain"}, timeout=10.0)
```

- `PUSHGATEWAY_URL` env var (no trailing slash). If empty, push is silently skipped.
- Push is best-effort: failure logs WARNING, does not abort the job.
- Prometheus scrapes Pushgateway with `honor_labels: true` so the `job` label from the
  push body is preserved.
- Metric names must match the alert rule expressions in `prometheus/rules.yml`.

## Access-control service (Phase 7)

### Port

- access-control: **8002** (host)

### Session mechanism

- **Storage**: `itsdangerous` `URLSafeSerializer` — signed cookie, server-side stateless.
  No Redis or DB session store needed.
- **Cookie name**: `pulsegrid_session`
- **TTL**: 8 hours (`SESSION_TTL_SECONDS = 8 * 3600`) — agent-chosen default, not a business rule.
  Override by changing the constant in `config.py`.
- **Payload**: `{"authenticated": bool, "name": str, "email": str, "expires_at": float}`.
  Signed, NOT encrypted — payload is visible to the client (base64). Acceptable because the
  payload contains only display name and email (not sensitive). If sensitive fields are ever
  added, switch to `itsdangerous.Fernet` or encrypt separately. See tech-debt-tracker.md.
- **CSRF protection**: pre-redirect `state` token stored in the session cookie; validated on
  callback before token exchange.

### MSAL ConfidentialClientApplication pattern

- Use `ConfidentialClientApplication` (not `PublicClientApplication`).
- Instantiate per request — MSAL is synchronous and not async-safe.
- Wrap all MSAL calls in `asyncio.to_thread(...)` when calling from FastAPI async routes.
- Scopes for identity-only login: `[]` (empty). MSAL automatically adds `openid`, `profile`,
  `offline_access` — passing them explicitly raises `ValueError: You cannot use any scope value
  that is reserved.` Do NOT include OIDC scopes in `AAD_SCOPES`.
- No Graph API calls needed for a login gate.

### Auth-gated route pattern

Routes that require authentication call `get_session(request)` then `is_authenticated(session)`,
and return `RedirectResponse(url="/auth/login", status_code=302)` if not authenticated.
FastAPI's `Depends()` mechanism cannot propagate a `RedirectResponse` return — use direct
inline checks in async route handlers (see `dashboard.py`).

### Dashboard content (agent-chosen defaults)

Three data sources, all fault-tolerant (each section degrades to an error notice independently):

1. **Reconciliation mismatches**: direct SQL read from CRM and ERP DBs. Counts:
   total CRM orders, orders matched to an ERP invoice, unmatched (mismatch).
   Same logic as reconciliation-job. No HTTP call — direct `sqlalchemy` sessions.
2. **LogPulse recent triage history**: `GET {LOGPULSE_URL}/history` with 5 s timeout.
   Returns up to 10 most recent items. Graceful fallback if endpoint unavailable.
3. **Service health**: `GET {CRM_SERVICE_URL}/health` and `GET {ERP_SERVICE_URL}/health`
   with 5 s timeout each. Shows green/yellow/red per service.

### No /metrics endpoint

access-control is a browser-facing UI service, not a data pipeline service.
There is no Prometheus scrape target for it. Do not add `prometheus-fastapi-instrumentator`.
This is an intentional exception to the standard FastAPI service pattern (Phase 6).

### Azure AD app registration (external/manual step)

The service consumes Azure AD credentials from env vars only. The actual app registration
(creating the app in Azure Portal, setting redirect URIs, generating client secret) is a
**manual step performed by the operator**. The agent does not automate Azure Portal interactions.
Steps required before running access-control:
1. Create an App Registration in Azure AD (Azure Portal → Azure Active Directory → App registrations).
2. Add Redirect URI: `http://localhost:8002/auth/callback` (or the production URI).
3. Create a client secret (Certificates & Secrets tab).
4. Copy Client ID, Tenant ID, Client Secret into `.env` (see `.env.example`).
5. Generate `SESSION_SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`.
6. Uncomment the `access-control` service in `observability-stack/docker-compose.yml`.


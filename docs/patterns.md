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
  docker-compose.yml  # DB only (no app service entry — run app locally with uv)
  pyproject.toml
  uv.lock
  .gitignore
```

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

## Ephemeral dedup in CI (GitHub Actions)

GitHub Actions runners are fresh per run — the SQLite dedup sidecar file does NOT
persist between workflow executions. This means the dedup cooldown has no effect across
runs in CI: every 15-minute run starts with an empty dedup store and will report
every failure it finds.

**For Phase 5 MVP this is acceptable** (each failure gets at most one LogPulse call per
run, not a burst). Future improvement: persist the dedup file via GitHub Actions cache
or a persistent external store. See tech-debt-tracker.md.


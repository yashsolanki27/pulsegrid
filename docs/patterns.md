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

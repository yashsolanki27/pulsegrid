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

- CRM↔ERP cross-service references (e.g. Invoice.crm_order_id) are soft references:
  no SQLAlchemy FK constraint, no DB-level constraint. Referential integrity is the
  responsibility of the calling service (integration-sync).

## Docker image

- Base: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`
- CMD: `uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port <port>`

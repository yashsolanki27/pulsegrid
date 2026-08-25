# crm-service Postman / Newman tests

Covers the implemented crm-service endpoints (customers, orders, tickets CRUD) plus
edge cases that are actually built today. Does **not** test anything unbuilt:
no ticket severity/status fields, no erp-service, no auth, no pagination.

## Files

- `crm-service.postman_collection.json` — self-contained collection (v2.1). No separate
  environment file needed; `baseUrl` and all ids are collection variables set by test scripts.

## Prerequisites

1. PostgreSQL reachable at `localhost:5432` with user/pass `postgres:postgres`
   and a database named `crm`. There is no docker-compose in this repo yet, so:

   ```
   docker run -d --name pulsegrid-crm-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=crm -p 5432:5432 postgres:16
   ```

2. Apply migrations (from `crm-service/`):

   ```
   uv run alembic upgrade head
   ```

3. Run the service (from `crm-service/`, default port 8000):

   ```
   uv run uvicorn app.main:app --port 8000
   ```

## Running via Newman

```
newman run postman/crm-service.postman_collection.json --env-var baseUrl=http://localhost:8000
```

Useful flags:

- `--reporters cli,junit --reporter-junit-export newman-report.xml` for CI output.
- `--delay-request 100` if hitting a slow remote instance.

## Notes / behavior assumptions (verified against code)

- Requests must run in order — ids chain through collection variables.
- Emails are timestamped per run (`alice.<epoch>@example.com`), so re-runs are safe
  even if a previous run's cleanup failed mid-way.
- Duplicate-customer 409 detail is a nested object:
  `{"detail": {"error": "duplicate customer", "existing_id": <id>}}`. All other errors are plain strings (`{"detail": "..."}`).
- Deleting a customer that still has orders/tickets → 409 (implemented guard);
  the suite exercises it before cleaning up dependents.
- Deleting an order that still has dependent tickets → 409 (`"order has dependent tickets"`,
  no cascade) — same FK-conflict handling as customer delete. The suite tests this
  while a ticket is still linked, then clears the link via PATCH before cleanup deletes.
- Ticket PATCH with `"order_id": null` intentionally clears the link — asserted as a happy path.

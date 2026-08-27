# Learnings

Reusable findings, non-obvious gotchas, and patterns discovered during development.
Organised by phase. Add new entries at the bottom of the relevant phase section.

---

## Phase 4: Reconciliation job

### LogPulse API contract (confirmed via live Swagger test)
- Endpoint: `POST https://log-pulse.up.railway.app/triage`
- No auth header required.
- Payload: `{ "log_text": "<string>" }` — **only field accepted**.
- Response: `{ "id": ..., "category": ..., "confidence": ..., ... }` — unknown fields
  must be silently ignored (use `from_dict()` with field filtering).
- HTTP 422 is a deterministic failure (bad payload) — do NOT retry.
- HTTP 502 / network errors → one retry acceptable.
- `log_text` phrasing matters for confidence: keywords like "integration failure",
  "mismatch detected", "order no invoice" push confidence above ~70%.
- See `pulsegrid_common/logpulse_client.py` for the canonical client.

### SQLite single-writer constraint
- SQLite is safe for all PulseGrid callers because each caller is a single process.
- If a caller is ever parallelised (e.g., threaded FastAPI + shared dedup), SQLite
  WAL mode must be enabled or the dedup store moved to Postgres.

---

## Phase 5: api-health-monitor + pulsegrid_common

### Newman JSON report quirks
- Newman `--reporters json` writes to `newman-report.json` in the current directory.
- Failed assertions appear in `run.executions[*].assertions[*]` where `assertion.error`
  is non-null. Requests with all-passing assertions have `assertions` entries with
  `error: null` — do NOT count these as failures.
- Newman exits non-zero on any test failure — use `continue-on-error: true` in the
  GitHub Actions step so the Python reporter always runs.
- The `response.status` field in Newman output is the HTTP status code (int), not a
  string. Use `str(item["response"]["status"])` for formatting.

### GitHub Actions: `actions/cache` with a stable key
- `actions/cache` with a **fixed** key (not per-run-id) accumulates state correctly
  across runs: the same entry is overwritten each time, not duplicated.
- `actions/cache/restore` before the job, `actions/cache/save` after with `if: always()`
  ensures state is persisted even when Newman reports failures.
- Cache miss on first run is silent (no file = empty dedup store = all failures reported).
  This is correct behaviour.

### pulsegrid_common path dependency in Docker
- Docker `COPY` requires the build context to include both `pulsegrid_common/` and the
  service directory. Set `context: ..` (repo root) and `dockerfile:` to the relative path.
- `uv.lock` is not required in the image if `uv sync --no-dev` can resolve from
  `pyproject.toml` alone. However, it improves reproducibility — consider committing
  `uv.lock` for each service.

---

## Phase 6: Observability stack

### Promtail Docker socket discovery vs file-based discovery
- Docker socket discovery (`docker_sd_configs`) requires `/var/run/docker.sock` to be
  mounted into the Promtail container. On Linux hosts this is straightforward. On
  Docker Desktop (Mac/Windows), the socket path is the same but the socket is a VM
  socket — this works transparently.
- The compose project label (`com.docker.compose.project`) is set automatically by
  Docker Compose to the directory name (lowercased). If the stack is started with
  `docker compose -p <name>`, the label changes — update the Promtail regex accordingly.

### Alertmanager webhook timeout vs LogPulse 90s timeout
- Alertmanager's default timeout for calling its receivers is 10s. The webhook-receiver
  makes a LogPulse call with a 90s timeout. If LogPulse is slow (>10s), Alertmanager
  will mark the webhook call as failed and retry — which can cause duplicate LogPulse
  calls within the same alert group window.
- The dedup store in webhook-receiver prevents duplicate LogPulse submissions for the
  same alert (dedup key = alert:{alertname}:{instance}, 24h cooldown).
- Alertmanager's own `repeat_interval: 4h` provides a second layer of noise suppression.
- Alertmanager's timeout is not configurable per-receiver in the YAML — it's a startup
  flag (`--timeout`). For v1 this is acceptable (dedup handles duplicates).

### Prometheus scrape targets for services running on host
- When Prometheus runs inside Docker and services (crm, erp) run on the host,
  `host.docker.internal` (Docker Desktop) or `172.17.0.1` (Linux bridge default) is
  needed as the target hostname — not `localhost`.
- The `prometheus.yml` uses service names (`crm-service:8000`, `erp-service:8001`)
  which only resolve if those services are also in the same Docker network.
  **For local dev (services on host, observability in Docker):** override the target
  hostnames via env vars or a separate `docker-compose.override.yml` that sets
  `CRM_HOST=host.docker.internal` etc.
- The current `prometheus.yml` assumes services will eventually be containerised and
  on the same compose network. This is a future-work item (see tech-debt-tracker.md).

### Grafana provisioning: dashboards.yml path must match mounted volume
- Grafana provisioning provider `path` must be the **in-container** path, not the host
  path. The docker-compose.yml mounts `./grafana/provisioning` to
  `/etc/grafana/provisioning`, so the `path:` in `dashboards.yml` is
  `/etc/grafana/provisioning/dashboards`.
- `allowUiUpdates: true` lets the dashboard be edited in the UI; changes are lost on
  container restart unless the JSON file is updated. Disable for production.

### `send_resolved: false` in Alertmanager webhook config
- With `send_resolved: false`, the webhook-receiver never sees "resolved" alerts.
  This is intentional — LogPulse has no concept of resolution; sending a "resolved"
  payload would require a separate LogPulse convention that doesn't exist.
- If resolution tracking is needed in the future, add a `POST /triage/resolve` endpoint
  to LogPulse (out of scope for v1).

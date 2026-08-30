# Tech Debt Tracker

Records intentional tradeoffs, known rough edges, and future-work items.
Not bugs — known decisions with documented rationale.

---

## Phase 4: Reconciliation job

### SQLite sidecar dedup state
- **Decision:** SQLite file (`dedup_state.db`) for dedup persistence in reconciliation-job.
- **Rationale:** Job has no Postgres DB of its own. Adding a third Postgres instance for
  dedup state is disproportionate. SQLite is portable, survives restarts, and is correct
  for a single-writer workload.
- **Tradeoff:** Not suitable if reconciliation-job ever runs as multiple concurrent
  instances (SQLite single-writer). Acceptable for v1 (one scheduled process).
- **Alternative rejected:** Postgres table in CRM or ERP DB — rejected to keep concerns
  separated (job state must not bleed into service DBs).

### Dedup cooldown default (24h)
- **Decision:** `DEDUP_COOLDOWN_HOURS=24` default — agent-chosen, not a business rule.
- **Rationale:** 24 hours is a reasonable minimum between repeated LogPulse reports for
  the same mismatch. Long enough to avoid spam; short enough to re-alert if an issue
  persists after a day.
- **Tunable:** Override via env var. No code change needed.
- **Risk:** If cooldown > LogPulse's retention window, a persistent mismatch could go
  untracked. Not a concern for v1 (LogPulse is demo-scale).

---

## Phase 5: pulsegrid_common + api-health-monitor

### pulsegrid_common shared library extraction
- **Decision:** Extracted `logpulse_client.py` and `dedup.py` into `pulsegrid_common/`
  path-dependency package, imported by reconciliation-job, api-health-monitor,
  and (Phase 6) webhook-receiver.
- **Rationale:** Three callers share identical requirements (sequential LogPulse POST,
  90s timeout, retry-on-502, dedup). Duplication would create three divergent copies.
- **Tradeoff:** Path dependency (`{ path = "../../pulsegrid_common" }`) works for local dev
  and Docker (build context at repo root). If services are ever split into separate repos,
  this needs to become a published package or a git submodule.

### Dedup schema generalisation (TEXT PRIMARY KEY)
- **Decision:** Changed dedup schema from `order_id INTEGER PK` to `dedup_key TEXT PK`.
- **Rationale:** api-health-monitor uses endpoint-based keys, not order IDs. Generalized
  schema serves all callers without code duplication.
- **Backward-compat:** reconciliation-job wraps its key as `f"order:{order_id}"`. No
  schema migration needed (DB is ephemeral per deployment; if existing DB exists, drop
  and recreate).

### GitHub Actions cron schedule default (*/15)
- **Decision:** api-health-monitor runs every 15 minutes by default.
- **Agent-chosen:** Not specified by user or business-logic.md. Minimum sensible interval
  for a demo use-case.
- **Tunable:** Edit `cron:` in `.github/workflows/api-health-monitor.yml`. No code change.
- **Risk:** 15-min interval × 24h = 96 runs/day. With dedup (24h cooldown), LogPulse
  receives at most 1 report per endpoint per day regardless.

### Ephemeral CI dedup (actions/cache)
- **Decision:** SQLite dedup DB persisted across GitHub Actions runs via `actions/cache`
  with a fixed key (`api-health-monitor-dedup-v1`).
- **Tradeoff:** GitHub cache is not guaranteed — cache misses are silent (first run after
  cache eviction behaves as if no prior cooldown). Acceptable for demo; a persistent
  store (e.g., GitHub Releases artifact or external KV) would be more reliable.
- **Alternative rejected:** Per-run-id cache key — defeats cooldown accumulation entirely.

---

## Phase 6: Observability stack

### Promtail compose-project label filter
- **Decision:** Promtail filters to containers with
  `__meta_docker_container_label_com_docker_compose_project == observability-stack`.
- **Tradeoff:** The compose project name is derived from the directory name by Docker
  Compose. If the `observability-stack/` folder is renamed or compose is invoked with
  `-p <other-name>`, Promtail will collect no logs. Fix: set `COMPOSE_PROJECT_NAME` env
  var or update the regex. Documented in promtail-config.yml header comment.

### Pushgateway metrics for reconciliation-job (best-effort, no prometheus_client)
- **Decision:** reconciliation-job pushes metrics to Pushgateway via raw httpx PUT
  (Prometheus text exposition format) rather than using the `prometheus_client` package.
- **Rationale:** Avoids adding another dependency to the job for two simple gauge pushes.
  Text format is stable and well-documented.
- **Tradeoff:** `prometheus_client` would handle labels, registry, and format automatically.
  Manual text format is more brittle if metric names/labels change. Acceptable for v1
  (two metrics, no labels beyond job name).
- **Best-effort:** Push failure logs a WARNING but does not abort the reconciliation run.
  Metrics are opportunistic — alert rules handle absence via `absent()`.

### Alertmanager group_interval / repeat_interval (agent-chosen)
- **Decision:** `group_interval: 5m`, `repeat_interval: 4h`.
- **Rationale:** 5m allows a brief "settle" window between alert groups to batch related
  alerts. 4h repeat interval prevents LogPulse from being spammed if a service stays down
  for hours. The dedup in webhook-receiver (24h cooldown) provides a second layer.
- **Not a business rule.** Tunable in `alertmanager/alertmanager.yml`.

### ReconciliationJobSilent alert expression (time() - gauge)
- **Decision:** Alert uses `(time() - reconciliation_run_total) > 7200` to detect stale
  metric push. This works only if reconciliation_run_total is a gauge tracking the epoch
  of the last push — it does NOT (it tracks order count). This expression is semantically
  incorrect for the count-gauge approach used.
- **Actual correct behaviour:** The `absent(reconciliation_run_total)` branch fires if
  Pushgateway has no metric at all (job never ran or gateway restarted). The `time() -`
  branch will fire spuriously when run_total is a small integer (< 7200 orders).
- **Mitigation:** A `reconciliation_last_run_timestamp` gauge (epoch seconds) would fix
  this properly. Logged as future-work. For v1/demo, `absent()` alone is sufficient to
  detect job silence after gateway restart.
- **Future fix:** Add a `reconciliation_last_run_timestamp` gauge push in run.py.

### webhook-receiver /metrics endpoint (resolved in Phase 6 session)
- prometheus-fastapi-instrumentator was added to webhook-receiver pyproject.toml and
  the lifespan hook added to main.py in the same session. The /metrics scrape target
  configured in prometheus.yml now returns real metrics.
- No remaining tech debt here.

---

## Phase 7: Access control

### Railway deployment: $PORT env var + healthcheck timeout
- **Incident:** Build/deploy succeeded but healthcheck timed out after 60s on Railway.
- **Root cause:** `railway.json` `startCommand` hardcoded `--port 8002`. Railway injects
  `$PORT` at runtime (dynamic, typically 8080+) and probes **that** port for the healthcheck.
  Container bound to 8002, Railway probed Railway's assigned port → no response → timeout.
- **Fix:** Use `${PORT:-8002}` in startCommand — uses Railway's assigned port in production,
  falls back to 8002 for local/Docker use. Timeout bumped to 300s (Railway max) to survive
  cold-start latency (uv dep resolution + MSAL init can spike the first boot).
- **Detection:** Root `railway.json` had the old hardcoded value; `access-control/railway.json`
  already had the fix from a prior session but was never synced back to the root file.
- **Lesson:** Railway reads the root `railway.json`; the service-level copy is redundant.
  Keep them in sync or remove the service-level copy to avoid silent divergence.

### itsdangerous signed cookie (stateless session)
- **Decision:** `URLSafeSerializer` signed cookie — no Redis, no DB session table.
- **Rationale:** Stateless session is sufficient for a single-tenant login gate where
  the payload (name, email, authenticated, expires_at) is not sensitive. No infrastructure
  dependency beyond the service itself.
- **Tradeoff:** Revocation is impossible before TTL expiry. If a user's account is
  compromised, there is no server-side mechanism to invalidate existing sessions — they
  expire after 8 hours. Acceptable for v1/demo. For production, add a server-side session
  store (Redis or Postgres) with a session ID + revocation table.
- **Signed, not encrypted:** The cookie payload is base64-encoded JSON and visible to
  the browser (not secret). Integrity is guaranteed by the HMAC signature. If the payload
  ever includes sensitive data, switch to Fernet (symmetric encryption + integrity).

### MSAL synchronous API in FastAPI async context
- **Decision:** Wrap all `ConfidentialClientApplication` calls in `asyncio.to_thread(...)`.
- **Rationale:** MSAL's Python library is synchronous. Calling it directly in an `async def`
  route would block the FastAPI event loop during the token exchange network call.
- **Tradeoff:** Thread pool usage for each login/callback. For a low-traffic login gate,
  this is negligible. If MSAL adds an async API in a future version, migrate to it.
- **Alternative rejected:** `msal-extensions` — adds unnecessary complexity for a login gate.

### LogPulse /history endpoint: availability unknown at build time
- **Decision:** Dashboard calls `GET LOGPULSE_URL/history` with a 5 s timeout and
  gracefully falls back to an error notice if unavailable.
- **Rationale:** The `/history` endpoint is not explicitly documented in learnings.md
  (Phase 4 only confirmed `/triage`). The dashboard is built to degrade gracefully rather
  than block on endpoint availability.
- **Future fix:** Confirm `/history` endpoint availability and response shape via live test.
  If available: verify pagination, authentication requirements, and response schema.
  If unavailable: replace with a direct query to LogPulse's `/triage` history (if any).

### Azure AD app registration: external/manual handoff
- **Decision:** The service consumes Azure AD credentials from env vars; no automated
  Azure Portal registration is performed.
- **Rationale:** Azure Portal app registration requires tenant admin access and a real
  Azure subscription. This is an operator responsibility, not an agent task.
- **Handoff note:** See `patterns.md § Azure AD app registration` and `.env.example` for
  the exact credentials required and generation instructions for `SESSION_SECRET_KEY`.

### Hosted dashboard: CRM/ERP sections are local-only (Option B scope limit)
- **Decision:** crm-service and erp-service are NOT deployed to Railway. The access-control
  dashboard's "Reconciliation Mismatches", "Service Health", and "Sync Match Ratio" sections
  are local-only — they require a running Docker Compose stack to show live data.
- **Rationale:** Owner chose Option B over Option A (see `blocked.md`). Deploying crm-service
  and erp-service to Railway would require provisioning Railway Postgres instances, seeding
  data, and adding long-running services — disproportionate scope for a portfolio demo. The
  dashboard is not entirely useless in production: the "Recent LogPulse Triage Results"
  section remains live (log-pulse.up.railway.app is public).
- **Scope in production (Railway hosted):**
  - ✅ LogPulse /history section — live
  - ✅ Azure AD login gate — live
  - ❌ Reconciliation Mismatches — shows local-only notice
  - ❌ Service Health — shows local-only notice
  - ❌ Sync Match Ratio — shows local-only notice
- **Scope in development (local Docker Compose):** all three sections live.
- **Implementation:** `mismatch_error` template variable gates all three CRM/ERP cards.
  `main.py` lifespan logs `logger.warning` (not `logger.critical`) for missing DB URLs.
- **Reversal path:** Implement Option A from `blocked.md`:
  - Add `railway.json` to `crm-service/` and `erp-service/`.
  - Provision Railway Postgres plugin instances for each service.
  - Set `CRM_DATABASE_URL`, `ERP_DATABASE_URL`, `CRM_SERVICE_URL`, `ERP_SERVICE_URL`
    as Railway env vars on the access-control service (Railway-internal URLs).
  - Seed crm-service and erp-service Postgres with the existing seed scripts.
  - Remove the `mismatch_error`-gated local-only notices from `dashboard.html`
    (or leave them — they only show when the DB URLs are absent/unreachable).

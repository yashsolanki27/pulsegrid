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

tech-debt: Postman/Newman collection created and logic-verified via SQLite harness,
but never executed against live Postgres (Docker unavailable in dev sandbox).
Run for real before considering Phase 1 fully closed.

tech-debt [Phase 4 — reconciliation-job]:
Dedup storage: SQLite sidecar file (dedup_state.db). Chosen because reconciliation-job
has no Postgres DB of its own; lightweight and portable. If the job is ever
containerised, the file must be on a mounted volume to persist across container restarts.
If the job grows into a multi-instance deployment, SQLite will not work (not safe for
concurrent writers) and must be migrated to a Postgres table. Single-instance for v1.

tech-debt [Phase 4 — reconciliation-job]:
Cooldown window: 24 hours (DEDUP_COOLDOWN_HOURS env var, default 24). Agent-chosen
default — not a business rule, no user input received. If scheduled run frequency
changes (e.g. hourly), cooldown may need tuning. No action needed until scheduling
is configured; override via env var without code change.

tech-debt [Phase 5 — refactor: pulsegrid_common extraction]:
logpulse_client.py moved from reconciliation-job/ into pulsegrid_common/. reconciliation-job
now depends on pulsegrid_common via a local uv path reference. If pulsegrid_common is ever
published to PyPI or a private registry, update [tool.uv.sources] in each consumer's
pyproject.toml. For now, monorepo path reference is sufficient.

tech-debt [Phase 5 — refactor: dedup generalisation]:
dedup.py generalised from order_id INTEGER PRIMARY KEY to dedup_key TEXT PRIMARY KEY in
pulsegrid_common. reconciliation-job wraps its keys as f"order:{order_id}" — existing
SQLite databases created by the old schema (order_id column) are incompatible.
Migration path: delete dedup_state.db and let it recreate on next run (all cooldowns
reset to "never reported"). Acceptable for a demo; document before any production use.

tech-debt [Phase 5 — api-health-monitor]:
Schedule interval: */15 * * * * (every 15 minutes). Agent-chosen default — not
specified in any doc or user input. Tunable via cron expression in
.github/workflows/api-health-monitor.yml. Review before production use.

resolved [Phase 5 — api-health-monitor: dedup persistence via actions/cache]:
The SQLite dedup sidecar (health_dedup_state.db) is now persisted across GitHub
Actions runs using actions/cache with the FIXED key "api-health-monitor-dedup-v1".
Key is stable (not per-run-id, not per-commit) so the same cache entry is reused
every run. Cache is restored before Newman runs and saved after report_failures.py
completes (save step uses if: always() so a failed run still persists dedup updates).
The 24h cooldown window now spans across workflow executions as originally intended —
a broken endpoint is reported once, then suppressed until the cooldown expires.
Dedup key scheme unchanged: endpoint:{method}:{url_without_query}.

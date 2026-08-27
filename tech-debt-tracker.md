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

tech-debt [Phase 5 — api-health-monitor: ephemeral dedup in CI]:
GitHub Actions runners are stateless — the SQLite dedup sidecar does not persist
between workflow runs. Cooldown window (24h default) has no cross-run effect: every
run starts with an empty dedup store. This means every 15-minute run that finds a
failure will call LogPulse once (not a burst within the run, but one call per run per
failing endpoint). Acceptable for demo scale. Future fix: persist dedup file via
GitHub Actions cache (actions/cache) or a remote KV store accessible from the runner.

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

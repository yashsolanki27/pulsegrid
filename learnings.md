# Learnings — Reusable Findings (PulseGrid)

Findings surfaced during implementation that future phases should know.

---

## LogPulse API quirks (confirmed Phase 4, August 2026)

**Source:** Live Swagger test + Harness Spec v2 section 8.

1. **No idempotency / dedup on their side.**
   Identical `log_text` sent twice creates two separate DB rows. PulseGrid must
   maintain its own dedup state (see patterns.md, reconciliation-job section).
   Consequence for all future LogPulse callers (Phase 5 api-health-monitor,
   Phase 6 webhook receiver): each caller needs its own dedup / cooldown strategy.

2. **No rate limiting on their side.**
   LogPulse will accept burst calls; PulseGrid is responsible for throttling.
   Rule: always process sequentially, never fire concurrent requests.

3. **Confidence threshold ~70%.**
   `log_text` must contain real error-keyword phrasing ("sync error",
   "integration failure", "mismatch detected") or LogPulse returns
   `category: unclassified` with low confidence. Generic or vague descriptions
   score badly. Craft `log_text` as if it were an actual system log line.

4. **Unversioned schema — deserialize defensively.**
   No `/v1` prefix, no changelog. Always use `TriageResult.from_dict()` pattern:
   filter to known fields, treat all as nullable. Unknown fields from future
   additions should be silently ignored, never cause a parse error.

5. **Retry policy: 502 / network errors only.**
   422 and 404 are deterministic (bad payload or bad URL) -- never retry those.
   Only 502 and transport-level errors (ConnectError, Timeout) warrant a retry.
   Recommended: one retry max, 90 s timeout per attempt.

6. **`log_text` persisted forever as `raw_text`, exposed via `/history`.**
   No TTL, no PII-scrubbing. Fine for synthetic seed data; do not put realistic
   PII in any `log_text` regardless.

7. **`category` is a closed 5-value enum, server-enforced.**
   Safe to switch/match on in reporting logic. Values confirmed stable via live test.

8. **No auth header required.**
   Confirmed via live 200 response with no Authorization header sent.
   Future phases: do not add auth headers to LogPulse calls.

---

## SQLite sidecar for job-level dedup state (Phase 4)

When a scheduled job needs to track "last reported" state and has no dedicated
Postgres DB, a SQLite sidecar file is a clean, portable solution for v1.
Key constraint: single-writer only. Must migrate to Postgres if job becomes
multi-instance. See tech-debt-tracker.md for the full note.

---

## Newman / GitHub Actions gotchas (Phase 5, August 2026)

**Source:** Phase 5 api-health-monitor implementation.

1. **Newman exits non-zero on assertion failure.**
   Use `continue-on-error: true` on the Newman step so subsequent steps (e.g.
   `report_failures.py`) still run. Without this, the workflow bails before
   LogPulse can be called — the opposite of what you want.

2. **Newman JSON reporter format — `executions` array.**
   The JSON reporter output (via `--reporter-json-export`) stores per-request data
   under `run.executions[*]`. Assertion failures are in `executions[*].assertions[*].error`
   (null if passed). Request URL is in `executions[*].request.url` — can be a dict
   with a `raw` key (full URL string) or a plain string depending on version. Always
   handle both. HTTP status is in `executions[*].response.code`.

3. **GitHub Actions cron: minimum interval is 1 minute.**
   GitHub Actions does not support sub-minute cron expressions. `*/15 * * * *`
   (every 15 min) is the finest practical granularity for scheduled health checks.
   Note: GitHub also throttles scheduled workflows on free plans — actual trigger
   time may lag by a few minutes under load. For SLA-sensitive monitoring, a
   dedicated uptime service (e.g. UptimeRobot, Better Uptime) is more reliable.

4. **Dedup state persisted via actions/cache.**
   Each GitHub Actions job runs on a fresh runner — local files vanish at job end.
   The SQLite dedup sidecar (`health_dedup_state.db`) is explicitly persisted using
   `actions/cache` with fixed key `api-health-monitor-dedup-v1`. Cache is restored
   before Newman and saved after `report_failures.py` (with `if: always()` so
   failed runs still update state). The `DEDUP_DB_PATH` env var must match the
   cached file path. See patterns.md §"Dedup persistence in CI" for full details.

5. **Newman `--env-var` overrides collection variables.**
   Collection variables (`{{crm_base_url}}`) are overridden at runtime with
   `--env-var "crm_base_url=<value>"`. This is the correct pattern for CI — do not
   hardcode URLs in the collection itself. GitHub Actions secrets are injected as
   environment variables and then passed through to Newman via the run step shell.

6. **Newman timeout flags.**
   Two separate flags: `--timeout-request <ms>` (per-request timeout) and
   `--timeout <ms>` (total run timeout). Set both in CI to avoid hanging jobs.
   Recommended: `--timeout-request 15000 --timeout 60000` for health checks.

---

## pulsegrid_common extraction pattern (Phase 5 refactor)

When two+ components need the same module, extract it into a shared package with
a local path dependency (`[tool.uv.sources]` in each consumer's `pyproject.toml`).

```toml
# In each consumer's pyproject.toml:
[tool.uv.sources]
pulsegrid-common = { path = "../pulsegrid_common" }
```

This avoids import path hacks (sys.path manipulation) and keeps dependency
management clean. Each consumer installs the shared package with `uv pip install -e .`
(editable mode) so local edits to pulsegrid_common are reflected immediately.


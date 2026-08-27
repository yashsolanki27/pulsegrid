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

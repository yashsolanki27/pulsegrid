RESOLVED [Phase 4]: Severity mapping -- LogPulse TriageRequest accepts only log_text (no severity field).
PulseGrid internal severity labels (order-no-invoice=high etc.) are not sent to LogPulse.
Confirmed via live Swagger test. See PulseGrid-Agent-Harness-Spec-v2.md section 8.

RESOLVED [Phase 4]: LogPulse real API contract confirmed via live Swagger test.
Endpoint: POST https://log-pulse.up.railway.app/triage, no auth, {log_text} only.
See PulseGrid-Agent-Harness-Spec-v2.md section 8 for full contract details.

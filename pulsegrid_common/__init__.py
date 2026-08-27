"""
pulsegrid_common
================
Shared library for PulseGrid components.

Exports:
  - logpulse_client: TriageResult dataclass + post_to_logpulse()
  - dedup: DedupStore — generic key/cooldown dedup via SQLite sidecar

Used by: reconciliation-job, api-health-monitor, observability webhook receiver.
"""

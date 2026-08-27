"""
api-health-monitor/report_failures.py
======================================
Post-Newman failure reporter.

Reads Newman's JSON reporter output, finds failed assertions (non-2xx responses
or assertion failures), deduplicates against the previous run's state, and reports
each new/cooldown-expired failure to LogPulse via pulsegrid_common.

This script is CI-triggered, not a long-running service. It is designed to run
immediately after the Newman step in GitHub Actions. It must be called only when
Newman has already produced its JSON output file.

LogPulse contract (per pulsegrid_common.logpulse_client):
  POST https://log-pulse.up.railway.app/triage
  Body: {"log_text": "<real error phrasing>"}
  No auth header. 90s timeout. One retry on 502/network error.

Dedup:
  Key format: "endpoint:{method}:{url_without_query}"
  Cooldown: DEDUP_COOLDOWN_HOURS (default 24h) — same tunable pattern as reconciliation-job.
  Storage: SQLite sidecar at DEDUP_DB_PATH (default ./health_dedup_state.db).

Environment variables:
  NEWMAN_REPORT_PATH    — path to Newman JSON reporter output file (required)
  LOGPULSE_URL          — default https://log-pulse.up.railway.app/triage
  DEDUP_DB_PATH         — default ./health_dedup_state.db
  DEDUP_COOLDOWN_HOURS  — default 24 (tunable, not a business rule)
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

# pulsegrid_common is installed as a path dependency (see pyproject.toml).
from pulsegrid_common.dedup import DedupStore
from pulsegrid_common.logpulse_client import post_to_logpulse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("api-health-monitor.reporter")

# ---- Configuration -----------------------------------------------------------

NEWMAN_REPORT_PATH = os.getenv("NEWMAN_REPORT_PATH", "")
LOGPULSE_URL = os.getenv("LOGPULSE_URL", "https://log-pulse.up.railway.app/triage")
DEDUP_DB_PATH = os.getenv("DEDUP_DB_PATH", "./health_dedup_state.db")
DEDUP_COOLDOWN_HOURS = int(os.getenv("DEDUP_COOLDOWN_HOURS", "24"))


# ---- Newman report parsing ---------------------------------------------------

def _load_report(path: str) -> dict:
    """Load and parse the Newman JSON reporter output. Exit on error."""
    p = Path(path)
    if not p.exists():
        log.error("Newman report not found at path: %s", path)
        sys.exit(1)
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        log.error("Failed to parse Newman JSON report: %s", exc)
        sys.exit(1)


def _normalise_url(raw_url: "str | dict") -> str:
    """
    Newman stores request URL as either a plain string or a dict with 'raw' key.
    Normalise to a plain string, stripping query params for the dedup key.
    """
    if isinstance(raw_url, dict):
        raw = raw_url.get("raw", str(raw_url))
    else:
        raw = str(raw_url)
    # Strip query string for dedup key stability across parameterised runs.
    parsed = urlparse(raw)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _extract_failures(report: dict) -> list[dict]:
    """
    Walk the Newman report and collect all failures.

    Returns a list of dicts:
      {
        "name": str,        # test/request name
        "method": str,      # HTTP method
        "url": str,         # normalised URL (no query)
        "status": int|None, # HTTP status code if available
        "errors": [str],    # list of failure messages
      }
    """
    failures = []

    runs = report.get("run", {}).get("executions", [])
    for execution in runs:
        item_name = execution.get("item", {}).get("name", "unknown")
        request = execution.get("request", {})
        method = request.get("method", "GET")
        raw_url = request.get("url", "")
        url = _normalise_url(raw_url)

        response = execution.get("response", {})
        status = response.get("code") if response else None

        # Collect assertion failures
        assertion_errors = []
        for assertion in execution.get("assertions", []):
            err = assertion.get("error")
            if err is not None:
                msg = err.get("message", str(err))
                assertion_errors.append(msg)

        if assertion_errors:
            failures.append(
                {
                    "name": item_name,
                    "method": method,
                    "url": url,
                    "status": status,
                    "errors": assertion_errors,
                }
            )

    return failures


# ---- Log-text construction ---------------------------------------------------

def _build_log_text(failure: dict) -> str:
    """
    Craft real-error-style log_text for LogPulse >= 70% confidence.
    Pattern mirrors reconciliation-job: include keywords "API health check failed",
    "integration failure", "endpoint", and the HTTP status where available.
    """
    method = failure["method"]
    url = failure["url"]
    status = failure["status"]
    name = failure["name"]
    errors = "; ".join(failure["errors"])

    status_part = f"returned {status}" if status is not None else "did not respond"

    return (
        f"API health check failed: {method} {url} {status_part}, "
        f"integration failure detected. "
        f"Test: \"{name}\". "
        f"Assertion errors: {errors}"
    )


# ---- Dedup key ---------------------------------------------------------------

def _dedup_key(failure: dict) -> str:
    """Stable dedup key: endpoint:{method}:{url} (no query string)."""
    return f"endpoint:{failure['method']}:{failure['url']}"


# ---- Main --------------------------------------------------------------------

def run() -> None:
    if not NEWMAN_REPORT_PATH:
        log.error(
            "NEWMAN_REPORT_PATH is not set. "
            "Pass the path to Newman's JSON output via this env var."
        )
        sys.exit(1)

    log.info(
        "Starting health-monitor report run. report=%s cooldown=%dh logpulse=%s",
        NEWMAN_REPORT_PATH,
        DEDUP_COOLDOWN_HOURS,
        LOGPULSE_URL,
    )

    report = _load_report(NEWMAN_REPORT_PATH)
    failures = _extract_failures(report)

    if not failures:
        log.info("No test failures found in Newman report -- nothing to report.")
        return

    log.info("Newman failures found: %d", len(failures))

    dedup = DedupStore(DEDUP_DB_PATH)
    cooldown = timedelta(hours=DEDUP_COOLDOWN_HOURS)
    now = datetime.now(tz=timezone.utc)

    reported = 0
    skipped = 0

    for failure in failures:
        key = _dedup_key(failure)
        last = dedup.get_last_reported(key)
        if last is not None and (now - last) < cooldown:
            log.info(
                "Skipped (cooldown): %s %s (last reported %s, cooldown %dh not expired)",
                failure["method"],
                failure["url"],
                last.isoformat(),
                DEDUP_COOLDOWN_HOURS,
            )
            skipped += 1
            continue

        log_text = _build_log_text(failure)
        log.info("Reporting to LogPulse: %s %s", failure["method"], failure["url"])

        result = post_to_logpulse(url=LOGPULSE_URL, log_text=log_text, timeout=90.0)

        if result is not None:
            dedup.mark_reported(key, now)
            reported += 1
            log.info(
                "Reported. triage_id=%s category=%s confidence=%s",
                result.id,
                result.category,
                result.confidence,
            )
        else:
            # Do NOT update dedup state -- let it retry on next scheduled run.
            log.warning(
                "LogPulse call failed for %s %s -- dedup NOT updated, will retry next run.",
                failure["method"],
                failure["url"],
            )

    log.info(
        "Run complete. reported=%d skipped=%d(cooldown) total_failures=%d",
        reported,
        skipped,
        len(failures),
    )


if __name__ == "__main__":
    run()

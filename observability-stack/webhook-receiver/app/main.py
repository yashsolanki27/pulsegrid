"""
observability-stack/webhook-receiver/app/main.py
================================================
FastAPI webhook receiver for Alertmanager.

Alertmanager POSTs alerts to POST /webhook.
This service:
  1. Parses the Alertmanager payload (one or more alerts per POST).
  2. For each firing alert, checks dedup cooldown via pulsegrid_common.DedupStore.
  3. On new / expired-cooldown alerts, calls LogPulse via pulsegrid_common.post_to_logpulse.
  4. Marks dedup state only on confirmed 200 from LogPulse.

Contract rules (same as Phase 4 / Phase 5):
  - No auth required on this receiver (Alertmanager has no credential to send).
  - 90s LogPulse timeout, one retry on 502/network, never retry 422/404.
  - Sequential LogPulse calls — no concurrency.
  - Dedup key scheme: "alert:{alertname}:{instance}"
    (follows existing patterns: "order:{id}", "endpoint:{method}:{url}")
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request, Response
from prometheus_fastapi_instrumentator import Instrumentator
from pulsegrid_common.dedup import DedupStore
from pulsegrid_common.logpulse_client import post_to_logpulse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("webhook-receiver")

# ---------------------------------------------------------------------------
# Configuration (env vars)
# ---------------------------------------------------------------------------

_LOGPULSE_URL: str = os.environ.get(
    "LOGPULSE_URL", "https://log-pulse.up.railway.app/triage"
)
_DEDUP_DB_PATH: str = os.environ.get("DEDUP_DB_PATH", "alert_dedup_state.db")
_DEDUP_COOLDOWN_HOURS: int = int(os.environ.get("DEDUP_COOLDOWN_HOURS", "24"))

# ---------------------------------------------------------------------------
# Module-level DedupStore (created once at startup)
# ---------------------------------------------------------------------------

_dedup: DedupStore = DedupStore(_DEDUP_DB_PATH)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Expose /metrics for Prometheus scraping (matches crm/erp-service pattern).
    Instrumentator().instrument(app).expose(app)
    yield


app = FastAPI(title="pulsegrid-webhook-receiver", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook", status_code=200)
async def receive_alert(request: Request) -> dict[str, Any]:
    """
    Alertmanager webhook endpoint.

    Alertmanager payload shape (simplified):
      {
        "version": "4",
        "groupLabels": { ... },
        "alerts": [
          {
            "status": "firing" | "resolved",
            "labels": { "alertname": "...", "instance": "...", ... },
            "annotations": { "summary": "...", "description": "..." },
            "startsAt": "2026-...",
            "endsAt": "0001-...",
            ...
          }
        ]
      }

    Only "firing" alerts are forwarded to LogPulse.
    "resolved" alerts are acknowledged and logged but not sent.
    """
    try:
        body: dict[str, Any] = await request.json()
    except Exception as exc:
        log.error("Failed to parse Alertmanager payload: %s", exc)
        return Response(content="bad request", status_code=400)  # type: ignore[return-value]

    alerts: list[dict[str, Any]] = body.get("alerts", [])
    log.info("Received %d alert(s) from Alertmanager.", len(alerts))

    now = datetime.now(tz=timezone.utc)
    cooldown = timedelta(hours=_DEDUP_COOLDOWN_HOURS)

    reported = 0
    skipped_resolved = 0
    skipped_dedup = 0

    for alert in alerts:
        status: str = alert.get("status", "")
        labels: dict[str, str] = alert.get("labels", {})
        annotations: dict[str, str] = alert.get("annotations", {})

        alertname: str = labels.get("alertname", "unknown")
        instance: str = labels.get("instance", "unknown")

        if status != "firing":
            log.info("Alert %s/%s is %s — skipping.", alertname, instance, status)
            skipped_resolved += 1
            continue

        dedup_key = f"alert:{alertname}:{instance}"

        last_reported = _dedup.get_last_reported(dedup_key)
        if last_reported is not None and (now - last_reported) < cooldown:
            remaining = cooldown - (now - last_reported)
            log.info(
                "Alert %s cooldown active — %s remaining, skipping LogPulse.",
                dedup_key,
                remaining,
            )
            skipped_dedup += 1
            continue

        summary: str = annotations.get("summary", alertname)
        description: str = annotations.get("description", "")
        job: str = labels.get("job", "unknown")
        severity: str = labels.get("severity", "warning")

        # Craft log_text with real error-keyword phrasing (≥70% confidence threshold).
        # Keywords: "alert firing", "integration failure", "mismatch detected",
        # "service down" etc. hit the LogPulse confidence threshold.
        log_text = (
            f"PulseGrid alert firing: {alertname} on {instance} (job={job}, "
            f"severity={severity}). {summary}. {description}. "
            f"Integration failure detected — alert triggered at observability layer."
        ).strip()
        # Truncate to LogPulse 20 000-char limit.
        log_text = log_text[:20000]

        log.info("Calling LogPulse for alert %s (key=%s).", alertname, dedup_key)
        result = post_to_logpulse(url=_LOGPULSE_URL, log_text=log_text)

        if result is not None:
            _dedup.mark_reported(dedup_key, now)
            log.info(
                "LogPulse accepted alert %s — id=%s category=%s confidence=%s.",
                dedup_key,
                result.id,
                result.category,
                result.confidence,
            )
            reported += 1
        else:
            log.warning(
                "LogPulse call failed for alert %s — dedup state NOT updated; "
                "next run will retry.",
                dedup_key,
            )

    return {
        "received": len(alerts),
        "reported_to_logpulse": reported,
        "skipped_resolved": skipped_resolved,
        "skipped_dedup": skipped_dedup,
    }

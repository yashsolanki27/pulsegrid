"""
pulsegrid_common/logpulse_client.py
=====================================
HTTP client for the LogPulse /triage endpoint.
Shared by reconciliation-job, api-health-monitor, and the observability webhook receiver.

Contract (confirmed via live Swagger test -- PulseGrid-Agent-Harness-Spec-v2.md section 8):
  POST https://log-pulse.up.railway.app/triage
  No auth header.
  Request:  {"log_text": "<1-20000 chars>"}
  Response: TriageResult (see dataclass below)

Key constraints:
  - Timeout: 90 s.
  - Retry: only on 502 / network-level errors (ConnectError, RemoteProtocolError, Timeout).
           NEVER retry 422/404 -- deterministic failures.
  - Sequential calls only (caller must not invoke concurrently).
  - TriageResult deserialized defensively: unknown fields ignored, all fields nullable-safe.
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger("pulsegrid_common.logpulse")

_RETRYABLE_STATUS = {502}
_MAX_RETRIES = 1


@dataclass
class TriageResult:
    """
    Defensive mirror of LogPulse TriageResult schema.
    All fields are nullable-safe; unknown fields from future schema additions are ignored.
    """

    id: "str | None" = None
    created_at: "str | None" = None
    raw_text: "str | None" = None
    extracted_error_line: "str | None" = None
    category: "str | None" = None
    root_cause_summary: "str | None" = None
    confidence: "int | None" = None
    suggested_action: "str | None" = None
    unclassified_reason: "str | None" = None
    sop_command: "str | None" = None

    @classmethod
    def from_dict(cls, data: "dict[str, Any]") -> "TriageResult":
        """
        Construct from a dict, ignoring any fields not declared in the dataclass.
        Defensive deserialization point -- future LogPulse schema additions will not
        break parsing here.
        """
        known = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def post_to_logpulse(
    url: str,
    log_text: str,
    timeout: float = 90.0,
) -> "TriageResult | None":
    """
    POST log_text to LogPulse /triage endpoint.

    Returns TriageResult on success.
    Returns None on any failure (caller must NOT update dedup state).

    Retry policy:
      - 502 or network/transport error -> one retry.
      - 422, 404, any other status -> no retry, return None immediately.
    """
    payload = {"log_text": log_text}
    attempts = 0

    while attempts <= _MAX_RETRIES:
        attempts += 1
        try:
            response = httpx.post(url, json=payload, timeout=timeout)
        except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.TimeoutException) as exc:
            log.warning(
                "LogPulse network error (attempt %d/%d): %s",
                attempts,
                _MAX_RETRIES + 1,
                exc,
            )
            if attempts > _MAX_RETRIES:
                log.error("LogPulse request failed after %d attempt(s) -- giving up.", attempts)
                return None
            log.info("Retrying LogPulse request...")
            continue
        except httpx.HTTPError as exc:
            log.error("LogPulse unexpected HTTP error: %s", exc)
            return None

        if response.status_code == 200:
            try:
                data = response.json()
                result = TriageResult.from_dict(data)
                log.debug("LogPulse response: %s", data)
                return result
            except Exception as exc:
                log.error(
                    "Failed to parse LogPulse response JSON: %s -- raw: %s",
                    exc,
                    response.text[:500],
                )
                return None

        if response.status_code in _RETRYABLE_STATUS:
            log.warning(
                "LogPulse returned %d (attempt %d/%d) -- retryable.",
                response.status_code,
                attempts,
                _MAX_RETRIES + 1,
            )
            if attempts > _MAX_RETRIES:
                log.error(
                    "LogPulse returned %d after %d attempt(s) -- giving up.",
                    response.status_code,
                    attempts,
                )
                return None
            log.info("Retrying LogPulse request...")
            continue

        # Non-retryable (422, 404, 500, etc.)
        log.error(
            "LogPulse returned non-retryable status %d: %s",
            response.status_code,
            response.text[:500],
        )
        return None

    return None

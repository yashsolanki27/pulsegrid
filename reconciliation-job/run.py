"""
reconciliation-job/run.py
=========================
Standalone scheduled script -- reads CRM and ERP DBs directly (not via HTTP),
detects orders with no matching ERP invoice, and reports new/cooldown-expired
mismatches to LogPulse.

Design decisions (also documented in patterns.md and tech-debt-tracker.md):

Dedup storage: SQLite sidecar file (default: ./dedup_state.db).
  Rationale: reconciliation-job has no Postgres DB of its own; a lightweight
  SQLite file avoids spinning up a third Postgres instance for a single small table.
  Portable -- survives restarts, works in Docker with a mounted volume.
  Single-writer workload (job is not concurrent) so SQLite is fully sufficient.

Cooldown window: 24 hours (DEDUP_COOLDOWN_HOURS env var, tunable).
  Rationale: prevents the same unresolved mismatch from spamming a new LogPulse
  triage entry on every scheduled run while still guaranteeing re-report if the
  gap persists across days. Not a business rule -- override as needed.

Imports: logpulse_client and DedupStore are imported from pulsegrid_common (shared
  library), not from local copies. Dedup key format: f"order:{order_id}" (generic
  string key as defined by pulsegrid_common.dedup.DedupStore).

Environment variables:
  CRM_DATABASE_URL      -- default postgresql+psycopg://postgres:postgres@localhost:5432/crm
  ERP_DATABASE_URL      -- default postgresql+psycopg://postgres:postgres@localhost:5433/erp
  DEDUP_DB_PATH         -- default ./dedup_state.db
  DEDUP_COOLDOWN_HOURS  -- default 24 (tunable, not a business rule)
  LOGPULSE_URL          -- default https://log-pulse.up.railway.app/triage
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from models import CRMOrder, ERPInvoice
from pulsegrid_common.dedup import DedupStore
from pulsegrid_common.logpulse_client import post_to_logpulse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("reconciliation-job")


# ---- Configuration -----------------------------------------------------------

CRM_DATABASE_URL = os.getenv(
    "CRM_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/crm",
)
ERP_DATABASE_URL = os.getenv(
    "ERP_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/erp",
)
DEDUP_DB_PATH = os.getenv("DEDUP_DB_PATH", "./dedup_state.db")
DEDUP_COOLDOWN_HOURS = int(os.getenv("DEDUP_COOLDOWN_HOURS", "24"))
LOGPULSE_URL = os.getenv("LOGPULSE_URL", "https://log-pulse.up.railway.app/triage")


# ---- DB connectivity ---------------------------------------------------------

def _make_engine(url: str, label: str):
    """Create engine and probe connectivity; sys.exit on failure."""
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("Connected to %s DB.", label)
        return engine
    except Exception as exc:
        log.error("Cannot connect to %s DB (%s): %s", label, url, exc)
        sys.exit(1)


# ---- Mismatch detection ------------------------------------------------------

def _fetch_crm_order_ids(session: Session) -> list:
    rows = session.query(CRMOrder.id).all()
    return [r.id for r in rows]


def _fetch_invoiced_order_ids(session: Session) -> set:
    rows = session.query(ERPInvoice.crm_order_id).all()
    return {r.crm_order_id for r in rows}


def _detect_mismatches(crm_ids: list, invoiced_ids: set) -> list:
    """Orders in CRM with no matching ERP invoice -- the ~10% intentional sync gap."""
    return [oid for oid in crm_ids if oid not in invoiced_ids]


# ---- Log-text construction ---------------------------------------------------

def _build_log_text(order_id: int) -> str:
    """
    Real error-style phrasing required for LogPulse confidence >= 70%.
    Keywords: "sync error", "mismatch detected" trigger correct classification.
    """
    return (
        f"Sync error: order {order_id} created in CRM, no matching invoice found in ERP "
        f"after integration-sync -- mismatch detected"
    )


# ---- Main reconciliation loop ------------------------------------------------

def run() -> None:
    log.info(
        "Starting reconciliation run. cooldown=%dh logpulse=%s",
        DEDUP_COOLDOWN_HOURS,
        LOGPULSE_URL,
    )

    crm_engine = _make_engine(CRM_DATABASE_URL, "CRM")
    erp_engine = _make_engine(ERP_DATABASE_URL, "ERP")

    with Session(crm_engine) as crm_session, Session(erp_engine) as erp_session:
        crm_ids = _fetch_crm_order_ids(crm_session)
        invoiced_ids = _fetch_invoiced_order_ids(erp_session)

    log.info(
        "CRM orders: %d | ERP invoices (matching CRM orders): %d",
        len(crm_ids),
        len(invoiced_ids),
    )

    mismatches = _detect_mismatches(crm_ids, invoiced_ids)
    log.info("Mismatches (no ERP invoice): %d", len(mismatches))

    if not mismatches:
        log.info("No mismatches -- nothing to report.")
        return

    dedup = DedupStore(DEDUP_DB_PATH)
    cooldown = timedelta(hours=DEDUP_COOLDOWN_HOURS)
    now = datetime.now(tz=timezone.utc)

    reported = 0
    skipped = 0

    for order_id in mismatches:
        dedup_key = f"order:{order_id}"
        last = dedup.get_last_reported(dedup_key)
        if last is not None and (now - last) < cooldown:
            log.info(
                "order_id=%d: skipped (last reported %s, cooldown %dh not expired)",
                order_id,
                last.isoformat(),
                DEDUP_COOLDOWN_HOURS,
            )
            skipped += 1
            continue

        log_text = _build_log_text(order_id)
        log.info("order_id=%d: posting to LogPulse...", order_id)

        result = post_to_logpulse(url=LOGPULSE_URL, log_text=log_text, timeout=90.0)

        if result is not None:
            dedup.mark_reported(dedup_key, now)
            reported += 1
            log.info(
                "order_id=%d: reported. triage_id=%s category=%s confidence=%s",
                order_id,
                result.id,
                result.category,
                result.confidence,
            )
        else:
            # Do NOT update dedup state -- let it retry on next run.
            log.warning(
                "order_id=%d: LogPulse call failed -- dedup NOT updated, will retry next run.",
                order_id,
            )

    log.info(
        "Run complete. reported=%d skipped=%d(cooldown) total_mismatches=%d",
        reported,
        skipped,
        len(mismatches),
    )


if __name__ == "__main__":
    run()

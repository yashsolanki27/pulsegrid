"""integration-sync — CRM→ERP synchronisation logic.

Triggered inside crm-service on order creation (not a standalone service).
Calls erp-service over HTTP to ensure:
  1. An ERP Account exists for the order's customer  (crm_customer_id soft-ref).
  2. A draft Invoice exists in ERP linked to the order (crm_order_id soft-ref).

INTENTIONAL FAILURE RATE (~10%)
================================
Before any network call is made, a feature-flagged random coin-flip has a
~10% chance of aborting the sync silently.  This is BY DESIGN — see
docs/business-logic.md §"CRM→ERP sync failure injection".

  • Do NOT remove, increase, or retry around this gate.
  • Do NOT raise the failure probability to 0 % (i.e. do NOT make sync
    100 % reliable).  The reconciliation-job (Phase 4) depends on real
    sync failures existing in the data set.
  • The SYNC_FAILURE_RATE environment variable controls the probability
    (default 0.10 = 10 %).  It exists only to aid testing; setting it to
    0 in production breaks the Phase 4 contract.

On success: ERP account is looked up (or created); draft invoice is created.
On failure (the ~10% silent-drop case): log at WARNING, return immediately —
  the calling order-creation endpoint must still succeed (HTTP 201).
On unexpected HTTP / network errors: log at ERROR, swallow the exception —
  same guarantee: order creation is never blocked by sync failures.
"""

import logging
import os
import random

import httpx

logger = logging.getLogger(__name__)

# ── Feature-flag ──────────────────────────────────────────────────────────────
# INTENTIONAL: ~10 % of syncs are silently dropped BY DESIGN.
# See docs/business-logic.md §"CRM→ERP sync failure injection".
# Changing this value toward 0 violates the Phase 3/4 design contract.
_SYNC_FAILURE_RATE: float = float(os.environ.get("SYNC_FAILURE_RATE", "0.10"))

# ── ERP service base URL ──────────────────────────────────────────────────────
_ERP_BASE_URL: str = os.environ.get("ERP_SERVICE_URL", "http://localhost:8001")


def _should_fail_this_sync() -> bool:
    """Return True ~SYNC_FAILURE_RATE of the time (the intentional failure gate).

    INTENTIONAL FAILURE INJECTION — do not remove or work around this gate.
    See module docstring for full rationale.
    """
    return random.random() < _SYNC_FAILURE_RATE


def _find_account_for_customer(client: httpx.Client, crm_customer_id: int) -> int | None:
    """Return ERP account id for crm_customer_id, or None if none exists."""
    resp = client.get(f"{_ERP_BASE_URL}/accounts")
    resp.raise_for_status()
    for acct in resp.json():
        if acct["crm_customer_id"] == crm_customer_id:
            return acct["id"]
    return None


def _ensure_account(client: httpx.Client, crm_customer_id: int) -> int:
    """Look up existing ERP account for customer; create one if absent.

    Returns the ERP account id.
    Account is always 1:1 with CRM customer (docs/business-logic.md).
    """
    account_id = _find_account_for_customer(client, crm_customer_id)
    if account_id is not None:
        logger.debug("integration-sync: found existing account %d for customer %d",
                     account_id, crm_customer_id)
        return account_id

    # No account yet — create with zero balance/credit_limit (defaults).
    resp = client.post(
        f"{_ERP_BASE_URL}/accounts",
        json={"crm_customer_id": crm_customer_id},
    )
    resp.raise_for_status()
    account_id = resp.json()["id"]
    logger.info("integration-sync: created account %d for customer %d",
                account_id, crm_customer_id)
    return account_id


def _create_invoice(client: httpx.Client, crm_order_id: int) -> int:
    """Create a draft invoice in ERP for the given CRM order id.

    Returns the new ERP invoice id.
    """
    resp = client.post(
        f"{_ERP_BASE_URL}/invoices",
        json={"crm_order_id": crm_order_id},
    )
    resp.raise_for_status()
    invoice_id = resp.json()["id"]
    logger.info("integration-sync: created invoice %d for order %d",
                invoice_id, crm_order_id)
    return invoice_id


def sync_order_to_erp(crm_order_id: int, crm_customer_id: int) -> None:
    """Trigger CRM→ERP sync after an order is successfully committed.

    INTENTIONAL FAILURE INJECTION (10 % gate — see module docstring):
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    If _should_fail_this_sync() returns True, the sync is silently aborted
    before any HTTP call is made.  A WARNING is logged; the caller must NOT
    retry and must NOT treat this as an error that blocks order creation.

    On unexpected errors from the ERP service, the exception is caught,
    logged at ERROR level, and swallowed — order creation is NEVER blocked
    by sync failures.
    """
    # ── INTENTIONAL FAILURE GATE — do NOT remove or bypass ───────────────────
    if _should_fail_this_sync():
        logger.warning(
            "integration-sync: intentional sync skip for order=%d customer=%d "
            "(~10%% failure rate, BY DESIGN — see docs/business-logic.md)",
            crm_order_id, crm_customer_id,
        )
        return
    # ─────────────────────────────────────────────────────────────────────────

    try:
        with httpx.Client(timeout=5.0) as client:
            _ensure_account(client, crm_customer_id)
            _create_invoice(client, crm_order_id)
        logger.info(
            "integration-sync: sync complete for order=%d customer=%d",
            crm_order_id, crm_customer_id,
        )
    except Exception as exc:  # noqa: BLE001
        # Any network / HTTP error is logged and swallowed.
        # Order creation must succeed regardless of sync outcome.
        logger.error(
            "integration-sync: sync error for order=%d customer=%d: %s",
            crm_order_id, crm_customer_id, exc,
        )

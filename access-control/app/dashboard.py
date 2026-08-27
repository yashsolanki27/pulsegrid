"""
access-control/app/dashboard.py
=================================
Dashboard route — assembles data from three sources and renders the HTML template.

Data sources:
  1. Reconciliation mismatches — direct DB read (CRM orders vs ERP invoices).
     Same logic as reconciliation-job: finds CRM order IDs with no matching ERP invoice.
  2. LogPulse /history — recent triage results. Graceful fallback if unavailable.
  3. Service health — HTTP GET /health on CRM and ERP services (5 s timeout).

Auth: require_auth dependency — any unauthenticated request is redirected to /auth/login.
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.config import (
    CRM_SERVICE_URL,
    ERP_SERVICE_URL,
    HEALTH_PING_TIMEOUT,
    LOGPULSE_URL,
)
from app.db import CRMSession, ERPSession
from app.session import get_session, is_authenticated

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Number of recent LogPulse history items to display
_LOGPULSE_HISTORY_LIMIT = 10


# ── / (dashboard) ─────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """
    Root route — renders the dashboard for authenticated users.
    Redirects to /auth/login for unauthenticated requests.
    """
    session = get_session(request)
    if not is_authenticated(session):
        return RedirectResponse(url="/auth/login", status_code=302)

    # Gather all data concurrently — each helper is individually fault-tolerant
    mismatch_data = _get_mismatch_counts()
    logpulse_data = await _get_logpulse_history()
    health_data = await _get_service_health()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user_name": session.get("name", "User"),
            "user_email": session.get("email", ""),
            **mismatch_data,
            **logpulse_data,
            **health_data,
        },
    )


# ── Data helpers ───────────────────────────────────────────────────────────────


def _get_mismatch_counts() -> dict[str, Any]:
    """
    Read CRM orders and ERP invoices directly from their respective DBs.
    Returns total_orders, matched_orders, mismatch_count.
    On DB error returns zeros with an error flag.
    """
    try:
        with CRMSession() as crm_db:
            total_orders: int = crm_db.execute(
                text("SELECT COUNT(*) FROM orders")
            ).scalar_one()
            crm_order_ids: set[int] = {
                row[0]
                for row in crm_db.execute(text("SELECT id FROM orders")).fetchall()
            }

        with ERPSession() as erp_db:
            erp_order_ids: set[int] = {
                row[0]
                for row in erp_db.execute(
                    text("SELECT crm_order_id FROM invoices WHERE crm_order_id IS NOT NULL")
                ).fetchall()
            }

        mismatched = crm_order_ids - erp_order_ids
        matched = len(crm_order_ids) - len(mismatched)

        return {
            "total_orders": total_orders,
            "matched_orders": matched,
            "mismatch_count": len(mismatched),
            "mismatch_error": None,
        }
    except Exception as exc:
        logger.warning("Dashboard: mismatch query failed: %s", exc)
        return {
            "total_orders": 0,
            "matched_orders": 0,
            "mismatch_count": 0,
            "mismatch_error": str(exc),
        }


async def _get_logpulse_history() -> dict[str, Any]:
    """
    Fetch recent triage results from LogPulse /history.
    Returns up to _LOGPULSE_HISTORY_LIMIT items.
    Gracefully falls back to an empty list + error message if the endpoint
    is unavailable or returns non-200 (see tech-debt-tracker.md Phase 7).
    """
    url = f"{LOGPULSE_URL}/history"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            items = resp.json()
            if isinstance(items, list):
                return {
                    "logpulse_history": items[:_LOGPULSE_HISTORY_LIMIT],
                    "logpulse_error": None,
                }
            # Unexpected shape
            return {
                "logpulse_history": [],
                "logpulse_error": "Unexpected response shape from LogPulse /history",
            }
        return {
            "logpulse_history": [],
            "logpulse_error": f"LogPulse /history returned HTTP {resp.status_code}",
        }
    except Exception as exc:
        logger.warning("Dashboard: LogPulse /history unavailable: %s", exc)
        return {
            "logpulse_history": [],
            "logpulse_error": f"LogPulse /history unavailable: {exc}",
        }


async def _get_service_health() -> dict[str, Any]:
    """
    Ping CRM and ERP /health endpoints with a short timeout.
    Returns per-service status: "ok", "degraded", or "unreachable".
    """

    async def _ping(label: str, base_url: str) -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=HEALTH_PING_TIMEOUT) as client:
                resp = await client.get(f"{base_url}/health")
            if resp.status_code == 200:
                return {"status": "ok", "code": str(resp.status_code)}
            return {"status": "degraded", "code": str(resp.status_code)}
        except Exception as exc:
            logger.warning("Dashboard: %s health ping failed: %s", label, exc)
            return {"status": "unreachable", "code": "—"}

    crm_health = await _ping("crm-service", CRM_SERVICE_URL)
    erp_health = await _ping("erp-service", ERP_SERVICE_URL)

    return {
        "crm_health": crm_health,
        "erp_health": erp_health,
    }

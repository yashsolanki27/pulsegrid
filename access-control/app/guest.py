"""
access-control/app/guest.py
============================
Guest / demo-mode routes.

Routes:
  GET /demo-login  — creates a read-only guest session and redirects to /
  GET /guest/      — home dashboard (guest-only, read-only)

The session cookie is *identical* to the one produced by the real Azure AD
flow:
  - Same itsdangerous URLSafeSerializer + salt
  - Same cookie name (pulsegrid_session)
  - Same TTL (SESSION_TTL_SECONDS)
  - Same payload schema, with one extra field: ``is_guest=True``

The real Azure AD flow (auth.py) is completely untouched. This route is
guarded by DEMO_MODE_ENABLED (config.py); if the flag is False or unset,
the endpoint returns HTTP 404 so it cannot be accidentally exposed in a
production deployment without explicitly enabling it.

Usage:
  GET /demo-login              → redirects to / with guest session set
  GET /demo-login?next=/foo    → redirects to /foo (restricted to /guest/* paths)
  GET /guest/                  → guest dashboard (requires guest session)
"""

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

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
from app.config import DEMO_MODE_ENABLED, SESSION_TTL_SECONDS
from app.models import (
    CRMCustomer, CRMOrder, CRMTicket,
    ERPInvoice, ERPInventoryItem, ERPAccount,
)
from app.session import get_session, is_authenticated, set_session

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Number of recent LogPulse history items to display
_LOGPULSE_HISTORY_LIMIT = 10

# Guest session payload constants
_GUEST_NAME = "Demo Guest"
_GUEST_EMAIL = "demo@pulsegrid.dev"


def _guest_required(request: Request) -> dict[str, Any] | RedirectResponse:
    """Check session is authenticated and is_guest. Returns session dict or redirect."""
    session = get_session(request)
    if not is_authenticated(session):
        return RedirectResponse(url="/auth/login", status_code=302)
    return session


# ── /demo-login ────────────────────────────────────────────────────────────────


@router.get("/demo-login", include_in_schema=False)
async def demo_login(request: Request):
    """
    Issue a read-only guest session and redirect to the dashboard.

    Returns HTTP 404 if DEMO_MODE_ENABLED is not True — this endpoint must be
    explicitly enabled via the DEMO_MODE_ENABLED=true env var before it works.

    The issued session is identical in structure to a real Azure AD session
    (authenticated=True, name, email, expires_at) plus is_guest=True so that
    templates can render a "Demo Mode" banner and suppress any write actions.
    """
    if not DEMO_MODE_ENABLED:
        logger.warning(
            "GET /demo-login called but DEMO_MODE_ENABLED is false — returning 404."
        )
        return HTMLResponse(
            content=(
                "<h1>404 Not Found</h1>"
                "<p>Demo mode is not enabled on this deployment.</p>"
            ),
            status_code=404,
        )

    guest_session = {
        "authenticated": True,
        "name": _GUEST_NAME,
        "email": _GUEST_EMAIL,
        "expires_at": time.time() + SESSION_TTL_SECONDS,
        "is_guest": True,
    }

    # Honour a `?next=` param but only allow /guest/* targets to prevent
    # open-redirect abuse (guest session cannot reach admin/auth routes).
    raw_next = request.query_params.get("next", "/")
    safe_next = raw_next if raw_next.startswith("/guest") else "/"

    response = RedirectResponse(url=safe_next, status_code=302)
    set_session(response, guest_session)

    logger.info("Guest session issued — redirecting to %s", safe_next)
    return response


# ── /guest/ (home dashboard) ──────────────────────────────────────────────────


@router.get("/guest/", response_class=HTMLResponse)
async def guest_home(request: Request):
    """Guest home dashboard — read-only, shows key metrics."""
    session = _guest_required(request)
    if isinstance(session, RedirectResponse):
        return session

    # Gather data — each helper is individually fault-tolerant
    mismatch_data = _get_mismatch_counts()
    logpulse_data = await _get_logpulse_history()
    health_data = await _get_service_health()

    return templates.TemplateResponse(
        request=request,
        name="guest_dashboard.html",
        context={
            "user_name": session.get("name", "Guest"),
            "user_email": session.get("email", ""),
            "is_guest": session.get("is_guest", False),
            "active_page": "home",
            **mismatch_data,
            **logpulse_data,
            **health_data,
        },
    )


# ── Data helpers (read-only, reused from dashboard.py pattern) ─────────────────


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
        logger.warning("Guest dashboard: mismatch query failed: %s", exc)
        return {
            "total_orders": 0,
            "matched_orders": 0,
            "mismatch_count": 0,
            "mismatch_error": str(exc),
        }


def _fmt_logpulse_item(item: dict) -> dict:
    """Format LogPulse created_at from ISO-8601 to human-readable."""
    _AMS = ZoneInfo("Europe/Amsterdam")
    raw = item.get("created_at")
    formatted = raw
    if raw:
        try:
            dt = datetime.fromisoformat(raw)
            dt = dt.astimezone(_AMS)
            formatted = dt.strftime("%b %-d, %Y, %-I:%M %p")
        except (ValueError, TypeError):
            pass
    return {**item, "created_at": formatted}


async def _get_logpulse_history() -> dict[str, Any]:
    """Fetch recent triage results from LogPulse /history."""
    url = f"{LOGPULSE_URL}/history"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            items = resp.json()
            if isinstance(items, list):
                sorted_items = sorted(
                    items, key=lambda x: x.get("id", 0), reverse=True
                )
                return {
                    "logpulse_history": [
                        _fmt_logpulse_item(item)
                        for item in sorted_items[:_LOGPULSE_HISTORY_LIMIT]
                    ],
                    "logpulse_error": None,
                }
            return {
                "logpulse_history": [],
                "logpulse_error": "Unexpected response shape from LogPulse /history",
            }
        return {
            "logpulse_history": [],
            "logpulse_error": f"LogPulse /history returned HTTP {resp.status_code}",
        }
    except Exception as exc:
        logger.warning("Guest dashboard: LogPulse /history unavailable: %s", exc)
        return {
            "logpulse_history": [],
            "logpulse_error": f"LogPulse /history unavailable: {exc}",
        }


async def _get_service_health() -> dict[str, Any]:
    """Ping CRM and ERP /health endpoints with a short timeout."""

    async def _ping(label: str, base_url: str) -> dict[str, str]:
        try:
            async with httpx.AsyncClient(timeout=HEALTH_PING_TIMEOUT) as client:
                resp = await client.get(f"{base_url}/health")
            if resp.status_code == 200:
                return {"status": "ok", "code": str(resp.status_code)}
            return {"status": "degraded", "code": str(resp.status_code)}
        except Exception as exc:
            logger.warning("Guest dashboard: %s health ping failed: %s", label, exc)
            return {"status": "unreachable", "code": "—"}

    crm_health = await _ping("crm-service", CRM_SERVICE_URL)
    erp_health = await _ping("erp-service", ERP_SERVICE_URL)

    return {
        "crm_health": crm_health,
        "erp_health": erp_health,
    }


# ── /guest/reconciliation ─────────────────────────────────────────────────────


def _get_reconciliation_rows() -> dict[str, Any]:
    """
    CRM orders with sync status — each order checked against ERP invoices.
    Returns rows: [{order_id, customer_name, order_date, synced}, ...].
    On DB error returns empty list with error flag.
    """
    try:
        with CRMSession() as crm_db:
            orders = crm_db.execute(
                text("SELECT id, customer_id, created_at FROM orders")
            ).fetchall()
            customers = {
                row[0]: row[1]
                for row in crm_db.execute(
                    text("SELECT id, name FROM customers")
                ).fetchall()
            }

        with ERPSession() as erp_db:
            erp_order_ids: set[int] = {
                row[0]
                for row in erp_db.execute(
                    text("SELECT crm_order_id FROM invoices WHERE crm_order_id IS NOT NULL")
                ).fetchall()
            }

        rows = []
        for order_id, customer_id, created_at in orders:
            raw_date = created_at or ""
            formatted_date = raw_date
            if raw_date:
                try:
                    from datetime import datetime
                    from zoneinfo import ZoneInfo

                    dt = datetime.fromisoformat(raw_date)
                    dt = dt.astimezone(ZoneInfo("Europe/Amsterdam"))
                    formatted_date = dt.strftime("%b %-d, %Y, %-I:%M %p")
                except (ValueError, TypeError):
                    pass
            rows.append({
                "order_id": order_id,
                "customer_name": customers.get(customer_id, "Unknown"),
                "order_date": formatted_date,
                "synced": order_id in erp_order_ids,
            })

        rows.sort(key=lambda r: r["order_id"], reverse=True)
        return {"reconciliation_rows": rows, "reconciliation_error": None}
    except Exception as exc:
        logger.warning("Guest reconciliation: query failed: %s", exc)
        return {"reconciliation_rows": [], "reconciliation_error": str(exc)}


@router.get("/guest/reconciliation", response_class=HTMLResponse)
async def guest_reconciliation(request: Request):
    """Guest reconciliation log — read-only CRM↔ERP sync status."""
    session = _guest_required(request)
    if isinstance(session, RedirectResponse):
        return session

    recon_data = _get_reconciliation_rows()

    return templates.TemplateResponse(
        request=request,
        name="guest_reconciliation.html",
        context={
            "user_name": session.get("name", "Guest"),
            "user_email": session.get("email", ""),
            "is_guest": session.get("is_guest", False),
            "active_page": "reconciliation",
            **recon_data,
        },
    )


# ── /guest/customers ─────────────────────────────────────────────────────────


def _get_customer_rows() -> dict[str, Any]:
    try:
        with CRMSession() as crm_db:
            customers = crm_db.query(CRMCustomer).order_by(CRMCustomer.id).all()
        rows = [[c.id, c.name or "—", c.email] for c in customers]
        return {
            "table_title": "Customers",
            "page_title": "CRM Customers",
            "columns": ["ID", "Name", "Email"],
            "rows": rows,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Guest customers: query failed: %s", exc)
        return {
            "table_title": "Customers",
            "page_title": "CRM Customers",
            "columns": ["ID", "Name", "Email"],
            "rows": [],
            "error": str(exc),
        }


@router.get("/guest/customers", response_class=HTMLResponse)
async def guest_customers(request: Request):
    session = _guest_required(request)
    if isinstance(session, RedirectResponse):
        return session
    data = _get_customer_rows()
    return templates.TemplateResponse(
        request=request,
        name="guest_list.html",
        context={
            "user_name": session.get("name", "Guest"),
            "user_email": session.get("email", ""),
            "is_guest": session.get("is_guest", False),
            "active_page": "customers",
            **data,
        },
    )


# ── /guest/orders ────────────────────────────────────────────────────────────


def _get_order_rows() -> dict[str, Any]:
    try:
        with CRMSession() as crm_db:
            orders = crm_db.query(CRMOrder).order_by(CRMOrder.id.desc()).all()
            customer_names = {
                c.id: c.name or "—"
                for c in crm_db.query(CRMCustomer).all()
            }
        rows = [
            [o.id, customer_names.get(o.customer_id, "Unknown"), o.created_at]
            for o in orders
        ]
        return {
            "table_title": "Orders",
            "page_title": "CRM Orders",
            "columns": ["ID", "Customer", "Created At"],
            "rows": rows,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Guest orders: query failed: %s", exc)
        return {
            "table_title": "Orders",
            "page_title": "CRM Orders",
            "columns": ["ID", "Customer", "Created At"],
            "rows": [],
            "error": str(exc),
        }


@router.get("/guest/orders", response_class=HTMLResponse)
async def guest_orders(request: Request):
    session = _guest_required(request)
    if isinstance(session, RedirectResponse):
        return session
    data = _get_order_rows()
    return templates.TemplateResponse(
        request=request,
        name="guest_list.html",
        context={
            "user_name": session.get("name", "Guest"),
            "user_email": session.get("email", ""),
            "is_guest": session.get("is_guest", False),
            "active_page": "orders",
            **data,
        },
    )


# ── /guest/tickets ───────────────────────────────────────────────────────────


def _get_ticket_rows() -> dict[str, Any]:
    try:
        with CRMSession() as crm_db:
            tickets = crm_db.query(CRMTicket).order_by(CRMTicket.id.desc()).all()
            customer_names = {
                c.id: c.name or "—"
                for c in crm_db.query(CRMCustomer).all()
            }
        rows = [
            [
                t.id,
                customer_names.get(t.customer_id, "Unknown"),
                t.subject,
                t.order_id or "—",
                t.created_at,
            ]
            for t in tickets
        ]
        return {
            "table_title": "Tickets",
            "page_title": "CRM Tickets",
            "columns": ["ID", "Customer", "Subject", "Order ID", "Created At"],
            "rows": rows,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Guest tickets: query failed: %s", exc)
        return {
            "table_title": "Tickets",
            "page_title": "CRM Tickets",
            "columns": ["ID", "Customer", "Subject", "Order ID", "Created At"],
            "rows": [],
            "error": str(exc),
        }


@router.get("/guest/tickets", response_class=HTMLResponse)
async def guest_tickets(request: Request):
    session = _guest_required(request)
    if isinstance(session, RedirectResponse):
        return session
    data = _get_ticket_rows()
    return templates.TemplateResponse(
        request=request,
        name="guest_list.html",
        context={
            "user_name": session.get("name", "Guest"),
            "user_email": session.get("email", ""),
            "is_guest": session.get("is_guest", False),
            "active_page": "tickets",
            **data,
        },
    )


# ── /guest/invoices ──────────────────────────────────────────────────────────


def _get_invoice_rows() -> dict[str, Any]:
    try:
        with ERPSession() as erp_db:
            invoices = erp_db.query(ERPInvoice).order_by(ERPInvoice.id.desc()).all()
        rows = [
            [i.id, i.crm_order_id, i.status, i.created_at]
            for i in invoices
        ]
        return {
            "table_title": "Invoices",
            "page_title": "ERP Invoices",
            "columns": ["ID", "CRM Order ID", "Status", "Created At"],
            "rows": rows,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Guest invoices: query failed: %s", exc)
        return {
            "table_title": "Invoices",
            "page_title": "ERP Invoices",
            "columns": ["ID", "CRM Order ID", "Status", "Created At"],
            "rows": [],
            "error": str(exc),
        }


@router.get("/guest/invoices", response_class=HTMLResponse)
async def guest_invoices(request: Request):
    session = _guest_required(request)
    if isinstance(session, RedirectResponse):
        return session
    data = _get_invoice_rows()
    return templates.TemplateResponse(
        request=request,
        name="guest_list.html",
        context={
            "user_name": session.get("name", "Guest"),
            "user_email": session.get("email", ""),
            "is_guest": session.get("is_guest", False),
            "active_page": "invoices",
            **data,
        },
    )


# ── /guest/inventory ─────────────────────────────────────────────────────────


def _get_inventory_rows() -> dict[str, Any]:
    try:
        with ERPSession() as erp_db:
            items = erp_db.query(ERPInventoryItem).order_by(ERPInventoryItem.id).all()
        rows = [[i.id, i.name, i.quantity, i.created_at] for i in items]
        return {
            "table_title": "Inventory",
            "page_title": "ERP Inventory",
            "columns": ["ID", "Name", "Quantity", "Created At"],
            "rows": rows,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Guest inventory: query failed: %s", exc)
        return {
            "table_title": "Inventory",
            "page_title": "ERP Inventory",
            "columns": ["ID", "Name", "Quantity", "Created At"],
            "rows": [],
            "error": str(exc),
        }


@router.get("/guest/inventory", response_class=HTMLResponse)
async def guest_inventory(request: Request):
    session = _guest_required(request)
    if isinstance(session, RedirectResponse):
        return session
    data = _get_inventory_rows()
    return templates.TemplateResponse(
        request=request,
        name="guest_list.html",
        context={
            "user_name": session.get("name", "Guest"),
            "user_email": session.get("email", ""),
            "is_guest": session.get("is_guest", False),
            "active_page": "inventory",
            **data,
        },
    )


# ── /guest/accounts ──────────────────────────────────────────────────────────


def _get_account_rows() -> dict[str, Any]:
    try:
        with ERPSession() as erp_db:
            accounts = erp_db.query(ERPAccount).order_by(ERPAccount.id).all()
        rows = [
            [a.id, a.crm_customer_id, f"{a.balance:,.2f}", f"{a.credit_limit:,.2f}", a.created_at]
            for a in accounts
        ]
        return {
            "table_title": "Accounts",
            "page_title": "ERP Accounts",
            "columns": ["ID", "CRM Customer ID", "Balance", "Credit Limit", "Created At"],
            "rows": rows,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Guest accounts: query failed: %s", exc)
        return {
            "table_title": "Accounts",
            "page_title": "ERP Accounts",
            "columns": ["ID", "CRM Customer ID", "Balance", "Credit Limit", "Created At"],
            "rows": [],
            "error": str(exc),
        }


@router.get("/guest/accounts", response_class=HTMLResponse)
async def guest_accounts(request: Request):
    session = _guest_required(request)
    if isinstance(session, RedirectResponse):
        return session
    data = _get_account_rows()
    return templates.TemplateResponse(
        request=request,
        name="guest_list.html",
        context={
            "user_name": session.get("name", "Guest"),
            "user_email": session.get("email", ""),
            "is_guest": session.get("is_guest", False),
            "active_page": "accounts",
            **data,
        },
    )

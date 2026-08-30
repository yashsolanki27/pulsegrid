"""
access-control/app/guest.py
============================
Guest / demo-mode auth route.

Route:
  GET /demo-login  — creates a read-only guest session and redirects to /

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
"""

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import DEMO_MODE_ENABLED, SESSION_TTL_SECONDS
from app.session import set_session

logger = logging.getLogger(__name__)

router = APIRouter()

# Guest session payload constants
_GUEST_NAME = "Demo Guest"
_GUEST_EMAIL = "demo@pulsegrid.dev"


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

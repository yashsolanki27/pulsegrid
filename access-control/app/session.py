"""
access-control/app/session.py
==============================
Session helpers using itsdangerous signed cookies.

Design:
  - Signed (not encrypted) cookie — payload is base64+json, tamper-evident but not
    confidential. For PulseGrid we only store name/email/authenticated/expires_at,
    which are not sensitive. If sensitive data is ever added, switch to Fernet
    encryption (see tech-debt-tracker.md).
  - Cookie name: pulsegrid_session
  - TTL: 8 hours (SESSION_TTL_SECONDS in config.py)
  - Server-side stateless — no Redis, no DB lookup on every request.

Session dict schema:
  {
    "authenticated": bool,
    "name": str,
    "email": str,
    "expires_at": float,   # Unix epoch seconds (UTC)
    "state": str,          # CSRF state stored pre-redirect, cleared post-callback
  }
"""

import time
from typing import Any

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeSerializer

from app.config import SESSION_COOKIE_NAME, SESSION_SECRET_KEY, SESSION_TTL_SECONDS


def _serializer() -> URLSafeSerializer:
    """Return the itsdangerous serializer. Created fresh each call (stateless)."""
    return URLSafeSerializer(SESSION_SECRET_KEY, salt="pulsegrid-session")


# ── Low-level cookie read/write ───────────────────────────────────────────────


def get_session(request: Request) -> dict[str, Any]:
    """
    Read and validate the signed session cookie.
    Returns an empty dict if missing, malformed, or tampered.
    """
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        return {}
    try:
        data: dict = _serializer().loads(raw)
    except (BadSignature, SignatureExpired, Exception):
        return {}
    return data


def set_session(response: Response, data: dict[str, Any]) -> None:
    """Write the signed session cookie onto *response*."""
    signed = _serializer().dumps(data)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=signed,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
    )


def clear_session(response: Response) -> None:
    """Delete the session cookie (logout)."""
    response.delete_cookie(key=SESSION_COOKIE_NAME)


# ── Auth check ────────────────────────────────────────────────────────────────


def is_authenticated(session: dict[str, Any]) -> bool:
    """
    Return True if the session contains a valid, non-expired authenticated flag.
    Checks both ``authenticated`` bool and ``expires_at`` epoch timestamp.
    """
    if not session.get("authenticated"):
        return False
    expires_at = session.get("expires_at", 0.0)
    return time.time() < expires_at


def require_auth(request: Request) -> dict[str, Any]:
    """
    FastAPI dependency — returns the session dict for authenticated users,
    or returns a RedirectResponse to /auth/login for unauthenticated requests.

    NOTE: FastAPI does not support raising RedirectResponse from a Depends().
    Instead, routes that use this dependency must check the return value:
        session = require_auth(request)
        if isinstance(session, RedirectResponse):
            return session

    A cleaner alternative is middleware; for this small service the inline
    check pattern is used (see dashboard.py).
    """
    session = get_session(request)
    if not is_authenticated(session):
        return RedirectResponse(url="/auth/login", status_code=302)  # type: ignore[return-value]
    return session

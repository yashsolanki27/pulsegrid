"""
access-control/app/auth.py
===========================
Azure AD OAuth2 Authorization Code flow via MSAL.

Routes:
  GET /auth/login    — initiates the MSAL auth code flow, redirects to Azure AD
  GET /auth/callback — handles the Azure AD callback, creates session, redirects to /
  GET /auth/logout   — clears session, redirects to /auth/login

MSAL notes (see learnings.md Phase 7):
  - ConfidentialClientApplication is synchronous — wrapped in asyncio.to_thread.
  - State parameter is stored in the session cookie before the redirect and
    validated on callback to prevent CSRF.
  - redirect_uri must exactly match the Azure AD app registration value (including
    scheme, host, port, path — trailing slash matters).
  - id_token claims: "name" (display name), "preferred_username" (email/UPN),
    "oid" (Azure AD object ID / unique user identifier).
"""

import asyncio
import secrets
import time

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from msal import ConfidentialClientApplication

from app.config import (
    AAD_AUTHORITY,
    AAD_CLIENT_ID,
    AAD_CLIENT_SECRET,
    AAD_REDIRECT_URI,
    AAD_SCOPES,
    SESSION_TTL_SECONDS,
)
from app.session import clear_session, get_session, set_session

router = APIRouter()


def _msal_app() -> ConfidentialClientApplication:
    """
    Build a fresh ConfidentialClientApplication per call.
    MSAL's ConfidentialClientApplication is not async-safe and holds an
    in-memory token cache; for a stateless login-gate with no token reuse,
    instantiating per request is the safest approach.
    """
    return ConfidentialClientApplication(
        client_id=AAD_CLIENT_ID,
        client_credential=AAD_CLIENT_SECRET,
        authority=AAD_AUTHORITY,
    )


# ── /auth/login ───────────────────────────────────────────────────────────────


@router.get("/auth/login")
async def auth_login(request: Request):
    """
    Initiate the OAuth2 Authorization Code flow.
    Generates a random state value, stores it in the session cookie,
    then redirects the browser to Azure AD's authorization endpoint.
    """
    state = secrets.token_urlsafe(16)

    # Store state in session (pre-auth session contains only the CSRF state)
    session = get_session(request)
    session["state"] = state

    # Get the authorization URL from MSAL (synchronous call — run in thread)
    app = _msal_app()
    auth_url: str = await asyncio.to_thread(
        app.get_authorization_request_url,
        scopes=AAD_SCOPES,
        state=state,
        redirect_uri=AAD_REDIRECT_URI,
    )

    response = RedirectResponse(url=auth_url, status_code=302)
    set_session(response, session)
    return response


# ── /auth/callback ────────────────────────────────────────────────────────────


@router.get("/auth/callback")
async def auth_callback(request: Request):
    """
    Azure AD posts back here with ?code=...&state=... after user logs in.

    Steps:
      1. Validate the state parameter (CSRF check).
      2. Exchange the auth code for tokens via MSAL.
      3. Extract claims from the id_token.
      4. Write an authenticated session cookie.
      5. Redirect to the dashboard (/}.
    """
    code: str | None = request.query_params.get("code")
    returned_state: str | None = request.query_params.get("state")
    error: str | None = request.query_params.get("error")
    error_desc: str | None = request.query_params.get("error_description", "")

    # Azure AD returned an error (e.g. user cancelled)
    if error:
        return RedirectResponse(
            url=f"/auth/login?error={error}&desc={error_desc}", status_code=302
        )

    if not code:
        return RedirectResponse(url="/auth/login?error=missing_code", status_code=302)

    # ── CSRF state validation ──────────────────────────────────────────────────
    session = get_session(request)
    expected_state = session.get("state")
    if not expected_state or expected_state != returned_state:
        return RedirectResponse(
            url="/auth/login?error=state_mismatch", status_code=302
        )

    # ── Exchange code for tokens ───────────────────────────────────────────────
    app = _msal_app()
    result: dict = await asyncio.to_thread(
        app.acquire_token_by_authorization_code,
        code=code,
        scopes=AAD_SCOPES,
        redirect_uri=AAD_REDIRECT_URI,
    )

    if "error" in result:
        error_msg = result.get("error_description", result.get("error", "unknown"))
        return RedirectResponse(
            url=f"/auth/login?error=token_error&desc={error_msg}", status_code=302
        )

    # ── Extract identity from id_token claims ──────────────────────────────────
    claims: dict = result.get("id_token_claims", {})
    name: str = claims.get("name", "Unknown User")
    email: str = claims.get("preferred_username", claims.get("email", "unknown@example.com"))

    # ── Write authenticated session ────────────────────────────────────────────
    auth_session = {
        "authenticated": True,
        "name": name,
        "email": email,
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }

    response = RedirectResponse(url="/", status_code=302)
    set_session(response, auth_session)
    return response


# ── /auth/logout ──────────────────────────────────────────────────────────────


@router.get("/auth/logout")
async def auth_logout(request: Request):
    """Clear the session cookie and redirect to login page."""
    response = RedirectResponse(url="/auth/login", status_code=302)
    clear_session(response)
    return response

"""
access-control/app/config.py
============================
Settings loaded from environment variables (via python-dotenv).
All Azure AD / session / DB / external-service settings live here.
"""

import os

from dotenv import load_dotenv

load_dotenv()


# ── Azure AD ──────────────────────────────────────────────────────────────────

AAD_CLIENT_ID: str = os.getenv("AAD_CLIENT_ID", "")
AAD_CLIENT_SECRET: str = os.getenv("AAD_CLIENT_SECRET", "")
AAD_TENANT_ID: str = os.getenv("AAD_TENANT_ID", "")
AAD_REDIRECT_URI: str = os.getenv("AAD_REDIRECT_URI", "http://localhost:8002/auth/callback")

# MSAL authority URL — single-tenant
AAD_AUTHORITY: str = f"https://login.microsoftonline.com/{AAD_TENANT_ID}"

# Scopes for identity-only login.
# NOTE: 'openid', 'profile', 'offline_access' are reserved by MSAL and added
# automatically — do NOT include them here or MSAL raises ValueError.
# For an auth-gate that only needs id_token claims (name, email), no extra scopes
# are required. MSAL will still return id_token_claims on callback.
AAD_SCOPES: list[str] = []


# ── Session ───────────────────────────────────────────────────────────────────

# Secret for itsdangerous SignedCookieSerializer.
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
SESSION_SECRET_KEY: str = os.getenv("SESSION_SECRET_KEY", "")
SESSION_COOKIE_NAME: str = "pulsegrid_session"
SESSION_TTL_SECONDS: int = 8 * 60 * 60  # 8 hours — agent-chosen default


# ── Service port ──────────────────────────────────────────────────────────────

ACCESS_CONTROL_PORT: int = int(os.getenv("ACCESS_CONTROL_PORT", "8002"))


# ── Databases ─────────────────────────────────────────────────────────────────

CRM_DATABASE_URL: str = os.getenv(
    "CRM_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/crm",
)
ERP_DATABASE_URL: str = os.getenv(
    "ERP_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/erp",
)


# ── External services ─────────────────────────────────────────────────────────

# Base URL only — no /triage suffix; dashboard calls /history
LOGPULSE_URL: str = os.getenv("LOGPULSE_URL", "https://log-pulse.up.railway.app")

# CRM / ERP service HTTP health check base URLs
CRM_SERVICE_URL: str = os.getenv("CRM_SERVICE_URL", "http://localhost:8000")
ERP_SERVICE_URL: str = os.getenv("ERP_SERVICE_URL", "http://localhost:8001")

# Timeout for health-ping HTTP calls (seconds)
HEALTH_PING_TIMEOUT: float = 5.0


# ── Guest / demo mode ─────────────────────────────────────────────────────────

# Set DEMO_MODE_ENABLED=true to enable the /demo-login endpoint that issues a
# read-only guest session without requiring Azure AD credentials.
# Leave unset or set to "false" (default) to return HTTP 404 on /demo-login.
# MUST be false in any deployment where real users' data is present.
# See docs/patterns.md § Guest/demo mode (Phase 8).
DEMO_MODE_ENABLED: bool = os.getenv("DEMO_MODE_ENABLED", "false").lower() == "true"

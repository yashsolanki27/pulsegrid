"""
access-control/app/main.py
===========================
FastAPI application entry point for the access-control service.

Routes:
  GET /          → dashboard (auth-gated, see dashboard.py)
  GET /auth/*    → Azure AD OAuth2 flow (see auth.py)
  GET /health    → liveness check (no auth required)

NOTE: /metrics is intentionally NOT exposed.
  access-control is a UI service (browser-facing), not a data service.
  There is no Prometheus scrape target for it.
  See patterns.md § Access-control service (Phase 7).
"""

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.auth import router as auth_router
from app.dashboard import router as dashboard_router


logger = logging.getLogger(__name__)

# GUID pattern — matches a Secret ID, NOT a secret value
_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup validation — catch misconfigurations before the first request."""
    from app.config import (
        AAD_CLIENT_ID,
        AAD_CLIENT_SECRET,
        AAD_TENANT_ID,
        CRM_DATABASE_URL,
        ERP_DATABASE_URL,
        SESSION_SECRET_KEY,
    )

    problems = []
    if not AAD_CLIENT_ID:
        problems.append("AAD_CLIENT_ID is not set")
    if not AAD_TENANT_ID:
        problems.append("AAD_TENANT_ID is not set")
    if not SESSION_SECRET_KEY:
        problems.append("SESSION_SECRET_KEY is not set")
    if not AAD_CLIENT_SECRET:
        problems.append("AAD_CLIENT_SECRET is not set")
    elif _GUID_RE.match(AAD_CLIENT_SECRET):
        problems.append(
            "AAD_CLIENT_SECRET looks like a Secret ID (GUID), not a Secret Value. "
            "In Azure Portal → App registrations → Certificates & secrets, copy the "
            "'Value' column (shown once at creation), NOT the 'Secret ID' column."
        )

    # CRM/ERP DB URLs are local-only data sources (Option B — no Railway deploy).
    # Their absence is expected in the hosted deployment; the dashboard degrades gracefully.
    if not CRM_DATABASE_URL:
        logger.warning(
            "Local-only data source unavailable in hosted deployment: CRM_DATABASE_URL"
        )
    if not ERP_DATABASE_URL:
        logger.warning(
            "Local-only data source unavailable in hosted deployment: ERP_DATABASE_URL"
        )

    if problems:
        for p in problems:
            logger.critical("CONFIG ERROR: %s", p)
        logger.critical(
            "access-control will start but auth/DB will fail until the above are fixed."
        )
    else:
        logger.info(
            "access-control config OK — AAD and session credentials present. "
            "CRM/ERP DB sections are local-only and will show notices in the hosted deployment."
        )

    yield


app = FastAPI(
    title="PulseGrid Access Control",
    description="Auth-gated dashboard — Azure AD OAuth2 login gate",
    version="1.0.0",
    lifespan=lifespan,
    # Disable the default OpenAPI UI in production-like mode
    # (login gate makes it irrelevant, but keep docs for dev convenience)
)

app.include_router(auth_router)
app.include_router(dashboard_router)


@app.get("/health", include_in_schema=False)
async def health():
    """Liveness endpoint — no auth required."""
    return JSONResponse({"status": "ok"})

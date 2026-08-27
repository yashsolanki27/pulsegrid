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

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.auth import router as auth_router
from app.dashboard import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No startup/shutdown tasks needed for this service.
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

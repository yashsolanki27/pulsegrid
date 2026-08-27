"""
access-control/app/db.py
=========================
Read-only SQLAlchemy sessions for CRM and ERP databases.

These are shadow connections — access-control never writes to CRM or ERP DBs.
Pattern mirrors reconciliation-job/run.py (direct DB read, not via HTTP).

NOTE: Engines are created lazily on first call to get_crm_session() /
get_erp_session() so that missing DB URLs do NOT crash the process at import
time. Startup validation is handled by the lifespan in main.py, which logs
CONFIG ERRORs and lets the /health endpoint remain reachable even when the
databases are not yet wired up (e.g. during Railway first-deploy setup).
"""

from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import CRM_DATABASE_URL, ERP_DATABASE_URL

logger = logging.getLogger(__name__)

# Module-level session factories — populated on first access, None until then.
_CRMSession: sessionmaker | None = None
_ERPSession: sessionmaker | None = None


def _crm_session_factory() -> sessionmaker:
    global _CRMSession
    if _CRMSession is None:
        if not CRM_DATABASE_URL:
            raise RuntimeError(
                "CRM_DATABASE_URL is not set. "
                "Set it in Railway → Variables "
                "(format: postgresql+psycopg://user:pass@host:port/dbname)."
            )
        engine = create_engine(CRM_DATABASE_URL, pool_pre_ping=True)
        _CRMSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return _CRMSession


def _erp_session_factory() -> sessionmaker:
    global _ERPSession
    if _ERPSession is None:
        if not ERP_DATABASE_URL:
            raise RuntimeError(
                "ERP_DATABASE_URL is not set. "
                "Set it in Railway → Variables "
                "(format: postgresql+psycopg://user:pass@host:port/dbname)."
            )
        engine = create_engine(ERP_DATABASE_URL, pool_pre_ping=True)
        _ERPSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return _ERPSession


def get_crm_session() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a read-only CRM DB session."""
    session = _crm_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_erp_session() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a read-only ERP DB session."""
    session = _erp_session_factory()()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Legacy aliases — kept so existing imports of CRMSession / ERPSession from
# this module continue to work without changes elsewhere in the codebase.
#
# dashboard.py calls these as context managers:  `with CRMSession() as db:`
# sessionmaker() returns a Session object which implements __enter__/__exit__,
# so the proxy just needs to delegate __call__ to the real factory.
# ---------------------------------------------------------------------------
class _LazySessionMaker:
    """Proxy that forwards __call__ to the real sessionmaker on first use.

    Usage patterns supported:
        session = CRMSession()          # plain call → Session object
        with CRMSession() as db:        # context manager (Session.__enter__)
            db.execute(...)
    """

    def __init__(self, factory_fn):
        self._factory = factory_fn

    def __call__(self, **kwargs):
        # Returns a Session instance (supports __enter__ / __exit__ natively)
        return self._factory()(**kwargs)


CRMSession = _LazySessionMaker(_crm_session_factory)
ERPSession = _LazySessionMaker(_erp_session_factory)

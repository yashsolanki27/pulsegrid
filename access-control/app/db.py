"""
access-control/app/db.py
=========================
Read-only SQLAlchemy sessions for CRM and ERP databases.

These are shadow connections — access-control never writes to CRM or ERP DBs.
Pattern mirrors reconciliation-job/run.py (direct DB read, not via HTTP).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import CRM_DATABASE_URL, ERP_DATABASE_URL

# Fail fast with a clear message if DB URLs are missing, rather than letting
# SQLAlchemy raise an opaque ArgumentError about an unparseable URL string.
if not CRM_DATABASE_URL:
    raise RuntimeError(
        "CRM_DATABASE_URL is not set. "
        "Set it in Railway → Variables (format: postgresql+psycopg://user:pass@host:port/dbname)."
    )
if not ERP_DATABASE_URL:
    raise RuntimeError(
        "ERP_DATABASE_URL is not set. "
        "Set it in Railway → Variables (format: postgresql+psycopg://user:pass@host:port/dbname)."
    )

# Separate engines for each DB — same pattern as crm-service / erp-service
_crm_engine = create_engine(CRM_DATABASE_URL, pool_pre_ping=True)
_erp_engine = create_engine(ERP_DATABASE_URL, pool_pre_ping=True)

CRMSession = sessionmaker(bind=_crm_engine, autocommit=False, autoflush=False)
ERPSession = sessionmaker(bind=_erp_engine, autocommit=False, autoflush=False)

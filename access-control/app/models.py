"""
access-control/app/models.py
=============================
Shadow ORM models for dashboard data queries.

These are READ-ONLY reflections of CRM and ERP tables.
No migrations — access-control never modifies these schemas.
Pattern mirrors reconciliation-job/models.py.
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped


class Base(DeclarativeBase):
    pass


# ── CRM shadow models ─────────────────────────────────────────────────────────


class CRMOrder(Base):
    """Shadow of crm.orders table — read-only."""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)


# ── ERP shadow models ─────────────────────────────────────────────────────────


class ERPInvoice(Base):
    """Shadow of erp.invoices table — read-only."""
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crm_order_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)

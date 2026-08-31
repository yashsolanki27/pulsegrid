"""
access-control/app/models.py
=============================
Shadow ORM models for dashboard data queries.

These are READ-ONLY reflections of CRM and ERP tables.
No migrations — access-control never modifies these schemas.
Pattern mirrors reconciliation-job/models.py.
"""

from sqlalchemy import Numeric, Integer, String
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped


class Base(DeclarativeBase):
    pass


# ── CRM shadow models ─────────────────────────────────────────────────────────


class CRMCustomer(Base):
    """Shadow of crm.customers table — read-only."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String)


class CRMOrder(Base):
    """Shadow of crm.orders table — read-only."""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String)


class CRMTicket(Base):
    """Shadow of crm.tickets table — read-only."""
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer)
    order_id: Mapped[int | None] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


# ── ERP shadow models ─────────────────────────────────────────────────────────


class ERPInvoice(Base):
    """Shadow of erp.invoices table — read-only."""
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crm_order_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class ERPInventoryItem(Base):
    """Shadow of erp.inventory table — read-only."""
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String)


class ERPAccount(Base):
    """Shadow of erp.accounts table — read-only."""
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crm_customer_id: Mapped[int] = mapped_column(Integer)
    balance: Mapped[float] = mapped_column(Numeric(12, 2))
    credit_limit: Mapped[float] = mapped_column(Numeric(12, 2))
    created_at: Mapped[str] = mapped_column(String)

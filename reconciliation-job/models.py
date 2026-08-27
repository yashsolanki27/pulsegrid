"""
Read-only ORM models for reconciliation-job.

These are *shadow* declarations — the canonical models live in crm-service
and erp-service respectively.  reconciliation-job only needs the columns it
actually reads; declaring them here avoids importing from the service packages
and keeps this script self-contained.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ── CRM shadow models ─────────────────────────────────────────────────────────

class CRMBase(DeclarativeBase):
    pass


class CRMOrder(CRMBase):
    """Shadow of crm-service orders table — only columns we need."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer(), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── ERP shadow models ─────────────────────────────────────────────────────────

class ERPBase(DeclarativeBase):
    pass


class ERPInvoice(ERPBase):
    """Shadow of erp-service invoices table — only columns we need."""

    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    crm_order_id: Mapped[int] = mapped_column(Integer(), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

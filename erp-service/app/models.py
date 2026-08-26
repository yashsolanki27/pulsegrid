from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    # crm_order_id is the foreign reference from crm-service (cross-DB link —
    # no SQLAlchemy FK constraint; referential integrity enforced at app layer).
    crm_order_id: Mapped[int] = mapped_column(Integer(), index=True)
    # status: plain string; no enum enforced at DB level in v1 scaffold.
    # Allowed values (e.g. "pending"/"paid") to be decided in business-logic.md
    # before Phase 3 integration-sync is built — see blocked.md.
    status: Mapped[str] = mapped_column(String(64), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InventoryItem(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    # quantity: non-negative enforced at app layer; DB constraint deferred
    # until business rules (backorder / negative-stock policy) are resolved —
    # see blocked.md.
    quantity: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# BLOCKED: Account entity schema not implemented.
# The purpose of "accounts" in the ERP context (financial ledger account,
# vendor/supplier account, or other) is not defined in any docs.
# See blocked.md — do not implement until unblocked.

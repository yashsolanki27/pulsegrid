import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    paid = "paid"
    overdue = "overdue"


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    # crm_order_id is the foreign reference from crm-service (cross-DB link —
    # no SQLAlchemy FK constraint; referential integrity enforced at app layer).
    crm_order_id: Mapped[int] = mapped_column(Integer(), index=True)
    # status: native Postgres enum column enforcing InvoiceStatus values.
    # Valid transitions enforced at service layer (see invoices router).
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoicestatus"),
        default=InvoiceStatus.draft,
        server_default="draft",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InventoryItem(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    # quantity: non-negative enforced at BOTH app layer (Pydantic ge=0) and
    # DB layer (CHECK constraint above). DB violation caught as 422 in router.
    quantity: Mapped[int] = mapped_column(Integer(), default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Account(Base):
    """Customer billing account — 1:1 soft reference to CRM customer.

    crm_customer_id mirrors the same cross-DB pattern as Invoice.crm_order_id:
    plain integer column, indexed, no DB-level FK constraint.  Referential
    integrity is the responsibility of the calling service.
    """

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Soft reference to crm-service customers.id — no FK constraint (cross-DB).
    crm_customer_id: Mapped[int] = mapped_column(Integer(), index=True)
    balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, server_default="0.00")
    credit_limit: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, server_default="0.00")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

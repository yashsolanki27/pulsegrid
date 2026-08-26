"""Add accounts table, invoicestatus enum, inventory quantity CHECK constraint.

Revision ID: 0002_accounts_invoice_enum_inventory_check
Revises: 0001_initial
Create Date: 2026-08-26

Resolves all three blocked.md items from the scaffold step:
  - Account entity (customer billing account, 1:1 soft ref to CRM customer)
  - Invoice.status changed from plain String to native Postgres enum
  - InventoryItem.quantity CHECK constraint (quantity >= 0)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_accounts_invoice_enum_inventory_check"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Postgres-native enum type name must match SQLAlchemy Enum(name=...) in models.py.
invoicestatus_enum = sa.Enum(
    "draft", "sent", "paid", "overdue", name="invoicestatus"
)


def upgrade() -> None:
    # 1. Create the Postgres enum type.
    invoicestatus_enum.create(op.get_bind(), checkfirst=True)

    # 2. Alter Invoice.status: String → invoicestatus enum.
    #    Existing rows had server_default="pending" (not a valid enum value);
    #    migrate them to "draft" before changing the column type.
    op.execute("UPDATE invoices SET status = 'draft'")
    op.alter_column(
        "invoices",
        "status",
        type_=invoicestatus_enum,
        existing_type=sa.String(64),
        existing_nullable=False,
        postgresql_using="status::invoicestatus",
        server_default="draft",
    )

    # 3. Add CHECK constraint to inventory.quantity.
    op.create_check_constraint(
        "ck_inventory_quantity_nonneg",
        "inventory",
        "quantity >= 0",
    )

    # 4. Create accounts table.
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Soft reference to crm-service customers.id — no FK constraint (cross-DB).
        sa.Column("crm_customer_id", sa.Integer(), nullable=False),
        sa.Column("balance", sa.Numeric(12, 2), server_default="0.00", nullable=False),
        sa.Column("credit_limit", sa.Numeric(12, 2), server_default="0.00", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_accounts_crm_customer_id", "accounts", ["crm_customer_id"])


def downgrade() -> None:
    op.drop_index("ix_accounts_crm_customer_id", table_name="accounts")
    op.drop_table("accounts")

    op.drop_constraint("ck_inventory_quantity_nonneg", "inventory", type_="check")

    # Revert Invoice.status back to String; convert enum values to strings first.
    op.alter_column(
        "invoices",
        "status",
        type_=sa.String(64),
        existing_type=invoicestatus_enum,
        existing_nullable=False,
        postgresql_using="status::text",
        server_default="pending",
    )
    invoicestatus_enum.drop(op.get_bind(), checkfirst=True)

"""initial schema: invoices, inventory

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-26

Note: accounts table not created — entity schema is BLOCKED (see blocked.md).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Cross-DB soft reference to crm-service orders.id — no FK constraint.
        sa.Column("crm_order_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_invoices_crm_order_id", "invoices", ["crm_order_id"])

    op.create_table(
        "inventory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        # quantity: no CHECK constraint in v1; business rules (backorder policy)
        # not yet defined — see blocked.md.
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # accounts table: BLOCKED — not created until entity schema is resolved.
    # See blocked.md.


def downgrade() -> None:
    op.drop_table("inventory")
    op.drop_index("ix_invoices_crm_order_id", table_name="invoices")
    op.drop_table("invoices")

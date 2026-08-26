"""Seed erp-service database with synthetic test data.

RUN-ONCE script (not idempotent by design). It refuses to run if the
invoices table already has rows, so rerunning never double-seeds.
Use --force to wipe and reseed.

Usage (from erp-service/):
    uv run alembic upgrade head   # ensure schema exists first
    uv run python -m scripts.seed

Requires ERP_DATABASE_URL or the default local Postgres:
    postgresql+psycopg://postgres:postgres@localhost:5433/erp

Fixtures chosen to exercise domain rules from business-logic.md:
- Invoices cover all four statuses: draft, sent, paid, overdue.
- Inventory has varied quantities including 0 (floor).
- Accounts are 1:1 with distinct crm_customer_id values (soft refs to CRM
  customers seeded by crm-service/scripts/seed.py — no FK enforced).
"""

import argparse
import sys
from datetime import datetime

from app.db import SessionLocal
from app.models import Account, InventoryItem, Invoice, InvoiceStatus

# (crm_order_id, status, created_at)
INVOICES = [
    (1, InvoiceStatus.draft,   "2025-01-20T10:00:00+00:00"),
    (2, InvoiceStatus.sent,    "2025-02-10T12:30:00+00:00"),
    (3, InvoiceStatus.paid,    "2025-03-01T09:45:00+00:00"),
    (4, InvoiceStatus.paid,    "2025-03-15T14:10:00+00:00"),
    (5, InvoiceStatus.overdue, "2025-04-20T11:25:00+00:00"),
    (6, InvoiceStatus.sent,    "2025-05-30T16:50:00+00:00"),
    (7, InvoiceStatus.draft,   "2025-06-18T08:05:00+00:00"),
    (8, InvoiceStatus.overdue, "2025-07-02T08:15:00+00:00"),
]

# (name, quantity, created_at)
INVENTORY_ITEMS = [
    ("Laptop Stand",         45, "2025-01-05T08:00:00+00:00"),
    ("USB-C Hub",           120, "2025-01-10T09:30:00+00:00"),
    ("Mechanical Keyboard",  30, "2025-02-14T11:00:00+00:00"),
    ("Webcam HD",            60, "2025-02-28T14:20:00+00:00"),
    ("Monitor Arm",          15, "2025-03-12T10:45:00+00:00"),
    ("Cable Management Kit", 90, "2025-04-01T13:00:00+00:00"),
    ("Ergonomic Mouse",      50, "2025-04-22T09:15:00+00:00"),
    ("Desk Mat XL",           0, "2025-05-07T16:30:00+00:00"),  # out of stock (floor)
    ("Laptop Sleeve 15in",   25, "2025-06-03T11:50:00+00:00"),
    ("HDMI Switch 4K",       40, "2025-07-19T08:40:00+00:00"),
]

# (crm_customer_id, balance, credit_limit, created_at)
# crm_customer_ids 1-8 mirror CRM seed customers (soft ref, no FK).
ACCOUNTS = [
    (1, "1250.00", "5000.00", "2025-01-15T10:00:00+00:00"),
    (2,  "340.50", "2000.00", "2025-02-05T14:00:00+00:00"),
    (3,    "0.00", "1500.00", "2025-02-22T11:30:00+00:00"),
    (4,  "875.25", "3000.00", "2025-03-10T09:00:00+00:00"),
    (5, "2100.00", "5000.00", "2025-04-03T08:45:00+00:00"),
    (6,   "99.99", "1000.00", "2025-05-12T13:20:00+00:00"),
    (7,  "450.00", "2500.00", "2025-06-01T10:10:00+00:00"),
    (8,    "0.00",  "500.00", "2025-08-02T17:00:00+00:00"),
]


def seed(force: bool) -> None:
    db = SessionLocal()
    try:
        existing = db.query(Invoice).count()
        if existing and not force:
            print(
                f"Refusing to seed: {existing} invoice(s) already exist.\n"
                "This script is run-once; use --force to wipe and reseed."
            )
            sys.exit(1)
        if force:
            db.query(Account).delete()
            db.query(InventoryItem).delete()
            db.query(Invoice).delete()
            db.commit()

        parse = lambda s: datetime.fromisoformat(s)

        invoices = [
            Invoice(crm_order_id=oid, status=status, created_at=parse(ts))
            for oid, status, ts in INVOICES
        ]
        db.add_all(invoices)

        items = [
            InventoryItem(name=name, quantity=qty, created_at=parse(ts))
            for name, qty, ts in INVENTORY_ITEMS
        ]
        db.add_all(items)

        accounts = [
            Account(
                crm_customer_id=cid,
                balance=balance,
                credit_limit=credit_limit,
                created_at=parse(ts),
            )
            for cid, balance, credit_limit, ts in ACCOUNTS
        ]
        db.add_all(accounts)
        db.commit()

        print(
            f"Seeded {len(invoices)} invoices, {len(items)} inventory items, "
            f"{len(accounts)} accounts."
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete all existing invoices/inventory/accounts before seeding",
    )
    args = parser.parse_args()
    seed(force=args.force)

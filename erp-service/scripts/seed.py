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

Accounts (5):
  crm_customer_ids 1-5 mirror the first five CRM seed customers
  (soft ref — no FK enforced; IDs 1-5 are stable once CRM is seeded).
  Plausible placeholder ints are safe: the ERP schema carries no DB-level FK.

Invoices (6 — one per account crm_order_id, covering all 4 statuses):
  Status is never set directly; instead each invoice is inserted as draft
  (the only valid initial status per the create path) and then advanced
  through valid transitions using _assert_valid_transition — the same guard
  the live API uses.  This makes the transition history explicit in the script:
    draft-only   : invoice stays at draft             (crm_order_id 1)
    draft→sent   : invoice advanced to sent           (crm_order_id 2)
    draft→sent→paid    : terminal paid state          (crm_order_id 3)
    draft→sent→overdue : terminal overdue state       (crm_order_id 4)
    draft→sent→paid    : second paid example          (crm_order_id 5)
    draft-only   : second draft example               (crm_order_id 6)

Inventory (8 items, all quantities > 0):
  No quantity=0 rows — seed data represents actively stocked items.
  The DB CHECK constraint (ck_inventory_quantity_nonneg) allows 0 at runtime,
  but seed rows intentionally use positive values to reflect realistic stock.

  crm_customer_id values 1-5 are plausible placeholder ints.  If crm-service
  is running and seeded, IDs 1-5 will exist.  If it is not running the soft
  reference is harmless — no DB FK is defined.
"""

import argparse
import sys
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import Account, InventoryItem, Invoice, InvoiceStatus
from app.routers.invoices import _assert_valid_transition

# ---------------------------------------------------------------------------
# Accounts: (crm_customer_id, balance, credit_limit, created_at)
# crm_customer_ids 1-5 — stable once CRM seed has run; safe as placeholders.
# ---------------------------------------------------------------------------
ACCOUNTS = [
    (1, "1250.00", "5000.00", "2025-01-15T10:00:00+00:00"),
    (2,  "340.50", "2000.00", "2025-02-05T14:00:00+00:00"),
    (3,    "0.00", "1500.00", "2025-02-22T11:30:00+00:00"),
    (4,  "875.25", "3000.00", "2025-03-10T09:00:00+00:00"),
    (5, "2100.00", "5000.00", "2025-04-03T08:45:00+00:00"),
]

# ---------------------------------------------------------------------------
# Invoices: (crm_order_id, transition_chain)
# Each invoice starts as draft; transition_chain lists subsequent statuses
# in order.  The seed calls _assert_valid_transition for each step so that
# any regression in the transition DAG is caught at seed time.
# Covers all four terminal/intermediate statuses: draft, sent, paid, overdue.
# ---------------------------------------------------------------------------
INVOICE_TRANSITIONS = [
    # crm_order_id, [steps after draft], created_at
    (1, [],                                           "2025-01-20T10:00:00+00:00"),  # draft
    (2, [InvoiceStatus.sent],                         "2025-02-10T12:30:00+00:00"),  # sent
    (3, [InvoiceStatus.sent, InvoiceStatus.paid],     "2025-03-01T09:45:00+00:00"),  # paid
    (4, [InvoiceStatus.sent, InvoiceStatus.overdue],  "2025-03-15T14:10:00+00:00"),  # overdue
    (5, [InvoiceStatus.sent, InvoiceStatus.paid],     "2025-04-20T11:25:00+00:00"),  # paid
    (6, [],                                           "2025-05-30T16:50:00+00:00"),  # draft
]

# ---------------------------------------------------------------------------
# Inventory: (name, quantity, created_at)
# All quantities > 0 — seed represents actively stocked items only.
# The DB CHECK constraint (ck_inventory_quantity_nonneg) permits 0 at runtime
# but seed data deliberately avoids it per the task spec.
# ---------------------------------------------------------------------------
INVENTORY_ITEMS = [
    ("Laptop Stand",          45, "2025-01-05T08:00:00+00:00"),
    ("USB-C Hub",            120, "2025-01-10T09:30:00+00:00"),
    ("Mechanical Keyboard",   30, "2025-02-14T11:00:00+00:00"),
    ("Webcam HD",             60, "2025-02-28T14:20:00+00:00"),
    ("Monitor Arm",           15, "2025-03-12T10:45:00+00:00"),
    ("Cable Management Kit",  90, "2025-04-01T13:00:00+00:00"),
    ("Ergonomic Mouse",       50, "2025-04-22T09:15:00+00:00"),
    ("HDMI Switch 4K",        40, "2025-07-19T08:40:00+00:00"),
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

        # -- Accounts --------------------------------------------------------
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

        # -- Invoices (with replayed transition history) ----------------------
        invoices = []
        for crm_order_id, transitions, ts in INVOICE_TRANSITIONS:
            inv = Invoice(
                crm_order_id=crm_order_id,
                status=InvoiceStatus.draft,
                created_at=parse(ts),
            )
            db.add(inv)
            db.flush()  # get inv.id assigned
            for next_status in transitions:
                _assert_valid_transition(inv.status, next_status)
                inv.status = next_status
            invoices.append(inv)

        # -- Inventory -------------------------------------------------------
        items = [
            InventoryItem(name=name, quantity=qty, created_at=parse(ts))
            for name, qty, ts in INVENTORY_ITEMS
        ]
        db.add_all(items)

        db.commit()

        status_counts = {}
        for inv in invoices:
            status_counts[inv.status.value] = status_counts.get(inv.status.value, 0) + 1

        print(
            f"Seeded {len(accounts)} accounts, "
            f"{len(invoices)} invoices "
            f"({', '.join(f'{k}={v}' for k, v in sorted(status_counts.items()))}), "
            f"{len(items)} inventory items (all qty > 0)."
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

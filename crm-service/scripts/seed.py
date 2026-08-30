"""Seed crm-service database with synthetic test data.

RUN-ONCE script (not idempotent by design). It refuses to run if the
customers table already has rows, so rerunning never double-seeds.
Use --force to wipe and reseed.

Usage (from crm-service/):
    uv run alembic upgrade head   # ensure schema exists first
    uv run python -m scripts.seed

Requires CRM_DATABASE_URL or the default local Postgres:
    postgresql+psycopg://postgres:postgres@localhost:5432/crm

Deliberate demo fixtures per business-logic.md dedup rule
("same email + different id = duplicate"):
- Customers 4 & 5 share email "sarah.connell@example.com" (different ids).
- Customer 1 has an order WITH a linked ticket.
- Ticket 3 has NO order (order_id NULL).

Phase 8 demo-gap orders (indices 8-11):
- 4 extra CRM orders with NO matching ERP invoice, creating deterministic
  reconciliation mismatches for the guest/demo mode screens.
- These are distinct from the intentional ~10% random sync failure rate —
  they are fixed seed data, not probabilistic.
- ERP seed.py deliberately skips crm_order_ids for these orders (indices 8-11).
"""

import argparse
import sys
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import Customer, Order, Ticket

CUSTOMERS = [
    # (name, email, created_at)
    ("Ava Mitchell", "ava.mitchell@example.com", "2025-01-14T09:12:00+00:00"),
    ("Liam Torres", "liam.torres@example.com", "2025-02-03T14:40:00+00:00"),
    ("Noah Patel", "noah.patel@example.com", "2025-02-21T11:05:00+00:00"),
    # Deliberate duplicate pair: same email, different ids.
    ("Sarah Connell", "sarah.connell@example.com", "2025-03-08T16:22:00+00:00"),
    ("Sarah Connell", "sarah.connell@example.com", "2025-06-19T10:47:00+00:00"),
    ("Mia Okafor", "mia.okafor@example.com", "2025-04-02T08:30:00+00:00"),
    ("Ethan Brooks", "ethan.brooks@example.com", "2025-05-11T13:55:00+00:00"),
    ("Zofia Nowak", "zofia.nowak@example.com", "2025-06-27T15:18:00+00:00"),
    ("Diego Ramirez", "diego.ramirez@example.com", "2025-07-15T09:03:00+00:00"),
    ("Hana Suzuki", "hana.suzuki@example.com", "2025-08-01T17:36:00+00:00"),
]

# (customer_index_into_CUSTOMERS, created_at)
ORDERS = [
    (0, "2025-01-20T10:00:00+00:00"),
    (1, "2025-02-10T12:30:00+00:00"),
    (2, "2025-03-01T09:45:00+00:00"),
    (3, "2025-03-15T14:10:00+00:00"),
    (5, "2025-04-20T11:25:00+00:00"),
    (6, "2025-05-30T16:50:00+00:00"),
    (7, "2025-07-02T08:15:00+00:00"),
    (9, "2025-08-05T13:40:00+00:00"),
    # ── Demo-gap orders (Phase 8) ──────────────────────────────────────────
    # These four orders intentionally have NO matching ERP invoice.
    # They create deterministic reconciliation mismatches for the guest demo
    # without touching the intentional ~10% random sync failure rate.
    # ERP seed skips crm_order_ids for orders at indices 8-11.
    (4, "2025-09-10T11:00:00+00:00"),   # demo gap #1
    (6, "2025-09-18T14:30:00+00:00"),   # demo gap #2
    (8, "2025-10-02T09:00:00+00:00"),   # demo gap #3
    (0, "2025-10-15T16:45:00+00:00"),   # demo gap #4
]

# (customer_idx, order_idx_or_None, subject, created_at)
TICKETS = [
    # Order-linked ticket: ticket on customer 0's order.
    (0, 0, "Order arrived with damaged packaging", "2025-01-24T09:20:00+00:00"),
    (1, None, "Cannot reset password on account portal", "2025-02-12T15:05:00+00:00"),
    # Order-less ticket (order_id NULL) per schema.
    (2, None, "Question about warranty coverage", "2025-03-04T10:42:00+00:00"),
    (3, 3, "Charged twice for order confirmation", "2025-03-18T11:58:00+00:00"),
    (5, 4, "Requesting size exchange", "2025-04-25T14:33:00+00:00"),
    (6, None, "Website shows wrong delivery estimate", "2025-06-02T09:11:00+00:00"),
    (8, 7, "Item missing from delivered box", "2025-08-07T16:27:00+00:00"),
]


def seed(force: bool) -> None:
    db = SessionLocal()
    try:
        existing = db.query(Customer).count()
        if existing and not force:
            print(
                f"Refusing to seed: {existing} customer(s) already exist.\n"
                "This script is run-once; use --force to wipe and reseed."
            )
            sys.exit(1)
        if force:
            db.query(Ticket).delete()
            db.query(Order).delete()
            db.query(Customer).delete()
            db.commit()

        parse = lambda s: datetime.fromisoformat(s)

        customers = [
            Customer(name=name, email=email, created_at=parse(ts))
            for name, email, ts in CUSTOMERS
        ]
        db.add_all(customers)
        db.flush()

        orders = [
            Order(customer_id=customers[cidx].id, created_at=parse(ts))
            for cidx, ts in ORDERS
        ]
        db.add_all(orders)
        db.flush()

        tickets = [
            Ticket(
                customer_id=customers[cidx].id,
                order_id=None if oidx is None else orders[oidx].id,
                subject=subject,
                created_at=parse(ts),
            )
            for cidx, oidx, subject, ts in TICKETS
        ]
        db.add_all(tickets)
        db.commit()

        print(
            f"Seeded {len(customers)} customers, {len(orders)} orders, "
            f"{len(tickets)} tickets."
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete all existing customers/orders/tickets before seeding",
    )
    args = parser.parse_args()
    seed(force=args.force)

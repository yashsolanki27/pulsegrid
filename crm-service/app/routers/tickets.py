from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Customer, Order, Ticket
from app.schemas import TicketCreate, TicketOut, TicketUpdate

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _get_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return ticket


def _get_customer_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return customer


def _validate_order_ref(
    db: Session, order_id: int | None, effective_customer_id: int
) -> None:
    # order_id provided but missing OR owned by a different customer → 404
    # (approved convention, same as missing FK target in orders router).
    if order_id is None:
        return
    order = db.get(Order, order_id)
    if order is None or order.customer_id != effective_customer_id:
        raise HTTPException(status_code=404, detail="order not found")


@router.post("", response_model=TicketOut, status_code=201)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    _get_customer_or_404(db, payload.customer_id)
    _validate_order_ref(db, payload.order_id, payload.customer_id)
    ticket = Ticket(
        customer_id=payload.customer_id,
        order_id=payload.order_id,
        subject=payload.subject,
    )
    db.add(ticket)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=404, detail="customer not found")
    db.refresh(ticket)
    return ticket


@router.get("", response_model=list[TicketOut])
def list_tickets(db: Session = Depends(get_db)):
    return db.scalars(select(Ticket).order_by(Ticket.id)).all()


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    return _get_ticket_or_404(db, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(
    ticket_id: int, payload: TicketUpdate, db: Session = Depends(get_db)
):
    ticket = _get_ticket_or_404(db, ticket_id)
    updates = payload.model_dump(exclude_unset=True)

    new_customer_id = updates.get("customer_id", ticket.customer_id)
    if "customer_id" in updates:
        _get_customer_or_404(db, updates["customer_id"])
    if "order_id" in updates:
        # Explicit null clears the link; non-null must exist and belong
        # to the effective (possibly updated) customer.
        _validate_order_ref(db, updates["order_id"], new_customer_id)
    elif (
        "customer_id" in updates
        and ticket.order_id is not None
    ):
        # Customer changed without touching order_id: existing order
        # link must still belong to the new customer.
        _validate_order_ref(db, ticket.order_id, new_customer_id)

    for field, value in updates.items():
        setattr(ticket, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=404, detail="customer not found")
    db.refresh(ticket)
    return ticket


@router.delete("/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = _get_ticket_or_404(db, ticket_id)
    db.delete(ticket)
    db.commit()

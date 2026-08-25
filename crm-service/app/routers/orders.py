from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Customer, Order, Ticket
from app.schemas import OrderCreate, OrderOut, OrderUpdate

router = APIRouter(prefix="/orders", tags=["orders"])


def _get_order_or_404(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


def _get_customer_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return customer


@router.post("", response_model=OrderOut, status_code=201)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    _get_customer_or_404(db, payload.customer_id)
    order = Order(customer_id=payload.customer_id)
    db.add(order)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=404, detail="customer not found")
    db.refresh(order)
    return order


@router.get("", response_model=list[OrderOut])
def list_orders(db: Session = Depends(get_db)):
    return db.scalars(select(Order).order_by(Order.id)).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    return _get_order_or_404(db, order_id)


@router.patch("/{order_id}", response_model=OrderOut)
def update_order(
    order_id: int, payload: OrderUpdate, db: Session = Depends(get_db)
):
    order = _get_order_or_404(db, order_id)
    updates = payload.model_dump(exclude_unset=True)
    if "customer_id" in updates:
        _get_customer_or_404(db, updates["customer_id"])
        order.customer_id = updates["customer_id"]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=404, detail="customer not found")
    db.refresh(order)
    return order


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = _get_order_or_404(db, order_id)
    # Explicit guard: the ORM nulls the nullable tickets.order_id FK on
    # parent delete instead of raising, so IntegrityError never fires here.
    dependent_tickets = db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.order_id == order_id)
    )
    if dependent_tickets:
        raise HTTPException(status_code=409, detail="order has dependent tickets")
    db.delete(order)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="order has dependent tickets",
        )
    return Response(status_code=204)

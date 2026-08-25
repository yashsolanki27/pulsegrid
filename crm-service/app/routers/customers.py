from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Customer
from app.schemas import CustomerCreate, CustomerOut, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["customers"])


def _get_customer_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return customer


def _check_duplicate(db: Session, email: EmailStr, exclude_id: int | None = None) -> None:
    stmt = select(Customer).where(Customer.email == email)
    if exclude_id is not None:
        stmt = stmt.where(Customer.id != exclude_id)
    existing = db.scalar(stmt.limit(1))
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "duplicate customer", "existing_id": existing.id},
        )


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    _check_duplicate(db, payload.email)
    customer = Customer(email=payload.email, name=payload.name)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    return db.scalars(select(Customer).order_by(Customer.id)).all()


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    return _get_customer_or_404(db, customer_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)
):
    customer = _get_customer_or_404(db, customer_id)
    updates = payload.model_dump(exclude_unset=True)
    if "email" in updates:
        _check_duplicate(db, updates["email"], exclude_id=customer_id)
    for field, value in updates.items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = _get_customer_or_404(db, customer_id)
    db.delete(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="customer has dependent orders or tickets",
        )
    return Response(status_code=204)

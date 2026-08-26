from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Invoice, InvoiceStatus
from app.schemas import InvoiceCreate, InvoiceOut, InvoiceUpdate

router = APIRouter(prefix="/invoices", tags=["invoices"])

# Valid forward transitions — no skipping, no reversal.
_ALLOWED_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.draft: {InvoiceStatus.sent},
    InvoiceStatus.sent: {InvoiceStatus.paid, InvoiceStatus.overdue},
    InvoiceStatus.paid: set(),
    InvoiceStatus.overdue: set(),
}


def _get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    return invoice


def _assert_valid_transition(current: InvoiceStatus, next_status: InvoiceStatus) -> None:
    """Raise 422 if the requested transition is not allowed."""
    if next_status not in _ALLOWED_TRANSITIONS[current]:
        allowed = sorted(s.value for s in _ALLOWED_TRANSITIONS[current])
        raise HTTPException(
            status_code=422,
            detail=(
                f"invalid status transition '{current.value}' → '{next_status.value}'. "
                f"Allowed next states: {allowed or ['none (terminal state)']}"
            ),
        )


@router.post("", response_model=InvoiceOut, status_code=201)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    invoice = Invoice(crm_order_id=payload.crm_order_id)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("", response_model=list[InvoiceOut])
def list_invoices(db: Session = Depends(get_db)):
    return db.scalars(select(Invoice).order_by(Invoice.id)).all()


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return _get_invoice_or_404(db, invoice_id)


@router.patch("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)
):
    invoice = _get_invoice_or_404(db, invoice_id)
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        _assert_valid_transition(invoice.status, updates["status"])
    for field, value in updates.items():
        setattr(invoice, field, value)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    db.delete(invoice)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="invoice has dependents")
    return Response(status_code=204)

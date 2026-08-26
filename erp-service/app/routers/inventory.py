from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import InventoryItem
from app.schemas import InventoryItemCreate, InventoryItemOut, InventoryItemUpdate

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _get_item_or_404(db: Session, item_id: int) -> InventoryItem:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="inventory item not found")
    return item


@router.post("", response_model=InventoryItemOut, status_code=201)
def create_item(payload: InventoryItemCreate, db: Session = Depends(get_db)):
    item = InventoryItem(name=payload.name, quantity=payload.quantity)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[InventoryItemOut])
def list_items(db: Session = Depends(get_db)):
    return db.scalars(select(InventoryItem).order_by(InventoryItem.id)).all()


@router.get("/{item_id}", response_model=InventoryItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    return _get_item_or_404(db, item_id)


@router.patch("/{item_id}", response_model=InventoryItemOut)
def update_item(
    item_id: int, payload: InventoryItemUpdate, db: Session = Depends(get_db)
):
    item = _get_item_or_404(db, item_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = _get_item_or_404(db, item_id)
    db.delete(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="inventory item has dependents")
    return Response(status_code=204)

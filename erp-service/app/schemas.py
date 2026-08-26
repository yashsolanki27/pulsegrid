from datetime import datetime

from pydantic import BaseModel, Field


class InvoiceCreate(BaseModel):
    crm_order_id: int


class InvoiceUpdate(BaseModel):
    status: str | None = Field(default=None, min_length=1)


class InvoiceOut(BaseModel):
    id: int
    crm_order_id: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InventoryItemCreate(BaseModel):
    name: str = Field(min_length=1)
    quantity: int = Field(default=0, ge=0)


class InventoryItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    quantity: int | None = Field(default=None, ge=0)


class InventoryItemOut(BaseModel):
    id: int
    name: str
    quantity: int
    created_at: datetime

    model_config = {"from_attributes": True}


# BLOCKED: AccountCreate / AccountOut not yet defined.
# Schema depends on resolving the "accounts" entity purpose — see blocked.md.

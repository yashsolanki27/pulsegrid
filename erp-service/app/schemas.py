from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import InvoiceStatus


class InvoiceCreate(BaseModel):
    crm_order_id: int


class InvoiceUpdate(BaseModel):
    status: InvoiceStatus | None = None


class InvoiceOut(BaseModel):
    id: int
    crm_order_id: int
    status: InvoiceStatus
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


class AccountCreate(BaseModel):
    crm_customer_id: int
    balance: Decimal = Field(default=Decimal("0.00"), ge=0)
    credit_limit: Decimal = Field(default=Decimal("0.00"), ge=0)


class AccountUpdate(BaseModel):
    balance: Decimal | None = Field(default=None, ge=0)
    credit_limit: Decimal | None = Field(default=None, ge=0)


class AccountOut(BaseModel):
    id: int
    crm_customer_id: int
    balance: Decimal
    credit_limit: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}

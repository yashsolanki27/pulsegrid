from datetime import datetime

from pydantic import BaseModel, EmailStr


class CustomerCreate(BaseModel):
    email: EmailStr
    name: str | None = None


class CustomerUpdate(BaseModel):
    email: EmailStr | None = None
    name: str | None = None


class CustomerOut(BaseModel):
    id: int
    email: EmailStr
    name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    customer_id: int


class OrderUpdate(BaseModel):
    customer_id: int | None = None


class OrderOut(BaseModel):
    id: int
    customer_id: int
    created_at: datetime

    model_config = {"from_attributes": True}

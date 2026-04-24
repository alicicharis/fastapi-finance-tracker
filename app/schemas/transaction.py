from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.transaction import TransactionType


class TransactionCreate(BaseModel):
    account_id: UUID
    category_id: UUID
    amount: Decimal
    type: TransactionType
    date: date
    description: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be greater than 0")
        return v


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    amount: Optional[Decimal] = None
    type: Optional[TransactionType] = None
    date: Optional[date] = None
    description: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("amount must be greater than 0")
        return v


class TransactionFilter(BaseModel):
    account_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    type: Optional[TransactionType] = None
    limit: int = 50
    offset: int = 0


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    account_id: UUID
    category_id: UUID
    amount: Decimal
    type: TransactionType
    date: date
    description: Optional[str]
    created_at: datetime

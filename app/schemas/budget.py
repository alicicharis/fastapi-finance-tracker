from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class BudgetCreate(BaseModel):
    category_id: UUID
    month: date
    amount_limit: Decimal

    @field_validator("amount_limit")
    @classmethod
    def amount_limit_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount_limit must be greater than 0")
        return v


class BudgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_limit: Optional[Decimal] = None

    @field_validator("amount_limit")
    @classmethod
    def amount_limit_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("amount_limit must be greater than 0")
        return v


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    category_id: UUID
    month: date
    amount_limit: Decimal
    created_at: datetime
    amount_spent: Decimal
    percent_used: float

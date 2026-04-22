from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.account import AccountType


class AccountCreate(BaseModel):
    name: str
    account_type: AccountType
    currency: str = "USD"

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if len(v) < 1:
            raise ValueError("name must not be empty")
        return v

    @field_validator("currency")
    @classmethod
    def currency_format(cls, v: str) -> str:
        import re
        if not re.match(r"^[A-Z]{3}$", v):
            raise ValueError("currency must be a 3-letter uppercase ISO 4217 code")
        return v


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    account_type: Optional[AccountType] = None
    currency: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def currency_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        if not re.match(r"^[A-Z]{3}$", v):
            raise ValueError("currency must be a 3-letter uppercase ISO 4217 code")
        return v


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    account_type: AccountType
    currency: str
    created_at: datetime

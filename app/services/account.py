from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.schemas.account import AccountCreate, AccountUpdate


class AccountError(Exception):
    pass


class AccountNotFound(AccountError):
    pass


async def create_account(db: AsyncSession, user_id: UUID, data: AccountCreate) -> Account:
    account = Account(
        user_id=user_id,
        name=data.name,
        account_type=data.account_type,
        currency=data.currency,
    )
    db.add(account)
    await db.flush()
    return account


async def list_accounts(db: AsyncSession, user_id: UUID) -> list[Account]:
    result = await db.execute(
        select(Account)
        .where(Account.user_id == user_id, Account.deleted_at.is_(None))
        .order_by(Account.created_at)
    )
    return list(result.scalars().all())


async def get_account(db: AsyncSession, user_id: UUID, account_id: UUID) -> Account:
    result = await db.execute(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.deleted_at.is_(None),
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise AccountNotFound(f"Account {account_id} not found")
    return account


async def update_account(db: AsyncSession, user_id: UUID, account_id: UUID, data: AccountUpdate) -> Account:
    account = await get_account(db, user_id, account_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await db.flush()
    return account


async def delete_account(db: AsyncSession, user_id: UUID, account_id: UUID) -> None:
    account = await get_account(db, user_id, account_id)
    account.deleted_at = datetime.now(timezone.utc)
    await db.flush()

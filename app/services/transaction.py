from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionFilter, TransactionUpdate


class TransactionError(Exception):
    pass


class TransactionNotFound(TransactionError):
    pass


async def _validate_account(db: AsyncSession, user_id: UUID, account_id: UUID) -> None:
    result = await db.execute(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise TransactionNotFound(f"Account {account_id} not found")


async def _validate_category(db: AsyncSession, user_id: UUID, category_id: UUID) -> None:
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            or_(Category.user_id == user_id, Category.user_id.is_(None)),
        )
    )
    if result.scalar_one_or_none() is None:
        raise TransactionNotFound(f"Category {category_id} not found")


async def create_transaction(db: AsyncSession, user_id: UUID, data: TransactionCreate) -> Transaction:
    await _validate_account(db, user_id, data.account_id)
    await _validate_category(db, user_id, data.category_id)
    transaction = Transaction(
        user_id=user_id,
        account_id=data.account_id,
        category_id=data.category_id,
        amount=data.amount,
        type=data.type,
        date=data.date,
        description=data.description,
    )
    db.add(transaction)
    await db.flush()
    return transaction


async def list_transactions(db: AsyncSession, user_id: UUID, filters: TransactionFilter) -> list[Transaction]:
    query = select(Transaction).where(Transaction.user_id == user_id)
    if filters.account_id is not None:
        query = query.where(Transaction.account_id == filters.account_id)
    if filters.category_id is not None:
        query = query.where(Transaction.category_id == filters.category_id)
    if filters.start_date is not None:
        query = query.where(Transaction.date >= filters.start_date)
    if filters.end_date is not None:
        query = query.where(Transaction.date <= filters.end_date)
    if filters.type is not None:
        query = query.where(Transaction.type == filters.type)
    query = query.order_by(Transaction.date.desc(), Transaction.created_at.desc())
    query = query.limit(filters.limit).offset(filters.offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_transaction(db: AsyncSession, user_id: UUID, transaction_id: UUID) -> Transaction:
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        raise TransactionNotFound(f"Transaction {transaction_id} not found")
    return transaction


async def update_transaction(db: AsyncSession, user_id: UUID, transaction_id: UUID, data: TransactionUpdate) -> Transaction:
    transaction = await get_transaction(db, user_id, transaction_id)
    updates = data.model_dump(exclude_unset=True)
    if "account_id" in updates:
        await _validate_account(db, user_id, updates["account_id"])
    if "category_id" in updates:
        await _validate_category(db, user_id, updates["category_id"])
    for field, value in updates.items():
        setattr(transaction, field, value)
    await db.flush()
    return transaction


async def delete_transaction(db: AsyncSession, user_id: UUID, transaction_id: UUID) -> None:
    transaction = await get_transaction(db, user_id, transaction_id)
    await db.delete(transaction)
    await db.flush()

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import extract, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.schemas.budget import BudgetCreate, BudgetResponse, BudgetUpdate


class BudgetError(Exception):
    pass


class BudgetNotFound(BudgetError):
    pass


class BudgetConflict(BudgetError):
    pass


async def _validate_category(db: AsyncSession, user_id: UUID, category_id: UUID) -> None:
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            or_(Category.user_id == user_id, Category.user_id.is_(None)),
        )
    )
    if result.scalar_one_or_none() is None:
        raise BudgetNotFound(f"Category {category_id} not found")


async def _compute_spent(db: AsyncSession, user_id: UUID, category_id: UUID, month: date) -> Decimal:
    result = await db.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.user_id == user_id,
            Transaction.category_id == category_id,
            Transaction.type == TransactionType.EXPENSE,
            extract("year", Transaction.date) == month.year,
            extract("month", Transaction.date) == month.month,
        )
    )
    total = result.scalar_one_or_none()
    return total if total is not None else Decimal("0")


def _to_response(budget: Budget, amount_spent: Decimal) -> BudgetResponse:
    percent_used = float(amount_spent / budget.amount_limit * 100) if budget.amount_limit else 0.0
    return BudgetResponse(
        id=budget.id,
        user_id=budget.user_id,
        category_id=budget.category_id,
        month=budget.month,
        amount_limit=budget.amount_limit,
        created_at=budget.created_at,
        amount_spent=amount_spent,
        percent_used=percent_used,
    )


async def create_budget(db: AsyncSession, user_id: UUID, data: BudgetCreate) -> BudgetResponse:
    await _validate_category(db, user_id, data.category_id)
    month = data.month.replace(day=1)
    budget = Budget(
        user_id=user_id,
        category_id=data.category_id,
        month=month,
        amount_limit=data.amount_limit,
    )
    db.add(budget)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as e:
        raise BudgetConflict("Budget for this category and month already exists") from e
    amount_spent = await _compute_spent(db, user_id, data.category_id, month)
    return _to_response(budget, amount_spent)


async def list_budgets(db: AsyncSession, user_id: UUID, month: date) -> list[BudgetResponse]:
    month = month.replace(day=1)
    result = await db.execute(
        select(Budget).where(Budget.user_id == user_id, Budget.month == month)
    )
    budgets = list(result.scalars().all())
    responses = []
    for budget in budgets:
        amount_spent = await _compute_spent(db, user_id, budget.category_id, month)
        responses.append(_to_response(budget, amount_spent))
    return responses


async def get_budget(db: AsyncSession, user_id: UUID, budget_id: UUID) -> BudgetResponse:
    result = await db.execute(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id)
    )
    budget = result.scalar_one_or_none()
    if budget is None:
        raise BudgetNotFound(f"Budget {budget_id} not found")
    amount_spent = await _compute_spent(db, user_id, budget.category_id, budget.month)
    return _to_response(budget, amount_spent)


async def update_budget(db: AsyncSession, user_id: UUID, budget_id: UUID, data: BudgetUpdate) -> BudgetResponse:
    result = await db.execute(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id)
    )
    budget = result.scalar_one_or_none()
    if budget is None:
        raise BudgetNotFound(f"Budget {budget_id} not found")
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(budget, field, value)
    await db.flush()
    amount_spent = await _compute_spent(db, user_id, budget.category_id, budget.month)
    return _to_response(budget, amount_spent)


async def delete_budget(db: AsyncSession, user_id: UUID, budget_id: UUID) -> None:
    result = await db.execute(
        select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id)
    )
    budget = result.scalar_one_or_none()
    if budget is None:
        raise BudgetNotFound(f"Budget {budget_id} not found")
    await db.delete(budget)
    await db.flush()


async def get_over_threshold(db: AsyncSession, user_id: UUID, threshold: float, month: date) -> list[BudgetResponse]:
    month = month.replace(day=1)
    result = await db.execute(
        select(Budget).where(Budget.user_id == user_id, Budget.month == month)
    )
    budgets = list(result.scalars().all())
    responses = []
    for budget in budgets:
        amount_spent = await _compute_spent(db, user_id, budget.category_id, month)
        if budget.amount_limit and amount_spent / budget.amount_limit >= Decimal(str(threshold)):
            responses.append(_to_response(budget, amount_spent))
    return responses

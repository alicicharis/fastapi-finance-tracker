from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.budget import BudgetCreate, BudgetResponse, BudgetUpdate
from app.services.budget import BudgetConflict, BudgetNotFound, create_budget, delete_budget, get_budget, list_budgets, update_budget

router = APIRouter()


@router.post("/", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create(body: BudgetCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        budget = await create_budget(db, current_user.id, body)
        await db.commit()
        return budget
    except BudgetNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    except BudgetConflict:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Budget for this category and month already exists")


@router.get("/", response_model=list[BudgetResponse])
async def list_all(month: Optional[str] = Query(None, description="YYYY-MM"), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if month is not None:
        try:
            parsed_month = date.fromisoformat(f"{month}-01")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="month must be in YYYY-MM format")
    else:
        today = date.today()
        parsed_month = today.replace(day=1)
    return await list_budgets(db, current_user.id, parsed_month)


@router.get("/{budget_id}", response_model=BudgetResponse)
async def get_one(budget_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await get_budget(db, current_user.id, budget_id)
    except BudgetNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")


@router.patch("/{budget_id}", response_model=BudgetResponse)
async def update(budget_id: UUID, body: BudgetUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        budget = await update_budget(db, current_user.id, budget_id, body)
        await db.commit()
        return budget
    except BudgetNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(budget_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        await delete_budget(db, current_user.id, budget_id)
        await db.commit()
    except BudgetNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")

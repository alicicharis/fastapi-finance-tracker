from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services.category import (
    CategoryDuplicate,
    CategoryForbidden,
    CategoryNotFound,
    create_category,
    delete_category,
    list_categories,
    update_category,
)

router = APIRouter()


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create(body: CategoryCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        category = await create_category(db, current_user.id, body)
        await db.commit()
        return category
    except CategoryDuplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category name already exists")


@router.get("/", response_model=list[CategoryResponse])
async def list_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await list_categories(db, current_user.id)


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update(category_id: UUID, body: CategoryUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        category = await update_category(db, current_user.id, category_id, body)
        await db.commit()
        return category
    except CategoryForbidden:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify default category")
    except CategoryNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    except CategoryDuplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category name already exists")


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(category_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        await delete_category(db, current_user.id, category_id)
        await db.commit()
    except CategoryForbidden:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify default category")
    except CategoryNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

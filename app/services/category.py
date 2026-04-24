from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryError(Exception):
    pass


class CategoryNotFound(CategoryError):
    pass


class CategoryForbidden(CategoryError):
    pass


class CategoryDuplicate(CategoryError):
    pass


async def list_categories(db: AsyncSession, user_id: UUID) -> list[Category]:
    result = await db.execute(
        select(Category)
        .where(or_(Category.user_id == user_id, Category.user_id.is_(None)))
        .order_by(Category.is_default.desc(), Category.name)
    )
    return list(result.scalars().all())


async def get_category(db: AsyncSession, user_id: UUID, category_id: UUID) -> Category:
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            or_(Category.user_id == user_id, Category.user_id.is_(None)),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise CategoryNotFound(f"Category {category_id} not found")
    return row


async def create_category(db: AsyncSession, user_id: UUID, data: CategoryCreate) -> Category:
    category = Category(user_id=user_id, name=data.name, is_default=False)
    db.add(category)
    try:
        await db.flush()
    except IntegrityError:
        raise CategoryDuplicate("Category name already exists")
    return category


async def update_category(
    db: AsyncSession, user_id: UUID, category_id: UUID, data: CategoryUpdate
) -> Category:
    row = await get_category(db, user_id, category_id)
    if row.is_default or row.user_id is None:
        raise CategoryForbidden("Cannot modify default category")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    try:
        await db.flush()
    except IntegrityError:
        raise CategoryDuplicate("Category name already exists")
    return row


async def delete_category(db: AsyncSession, user_id: UUID, category_id: UUID) -> None:
    row = await get_category(db, user_id, category_id)
    if row.is_default or row.user_id is None:
        raise CategoryForbidden("Cannot modify default category")
    await db.delete(row)
    await db.flush()

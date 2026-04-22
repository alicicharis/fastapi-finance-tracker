from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate
from app.services.account import AccountNotFound, create_account, delete_account, get_account, list_accounts, update_account

router = APIRouter()


@router.post("/", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create(body: AccountCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await create_account(db, current_user.id, body)
    await db.commit()
    return account


@router.get("/", response_model=list[AccountResponse])
async def list_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await list_accounts(db, current_user.id)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_one(account_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await get_account(db, current_user.id, account_id)
    except AccountNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")


@router.patch("/{account_id}", response_model=AccountResponse)
async def update(account_id: UUID, body: AccountUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        account = await update_account(db, current_user.id, account_id, body)
        await db.commit()
        return account
    except AccountNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(account_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        await delete_account(db, current_user.id, account_id)
        await db.commit()
    except AccountNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

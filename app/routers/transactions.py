from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionFilter, TransactionResponse, TransactionUpdate
from app.services.transaction import TransactionNotFound, create_transaction, delete_transaction, get_transaction, list_transactions, update_transaction

router = APIRouter()


@router.post("/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create(body: TransactionCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        transaction = await create_transaction(db, current_user.id, body)
        await db.commit()
        return transaction
    except TransactionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account or category not found")


@router.get("/", response_model=list[TransactionResponse])
async def list_all(filters: TransactionFilter = Depends(), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await list_transactions(db, current_user.id, filters)


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_one(transaction_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await get_transaction(db, current_user.id, transaction_id)
    except TransactionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update(transaction_id: UUID, body: TransactionUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        transaction = await update_transaction(db, current_user.id, transaction_id, body)
        await db.commit()
        return transaction
    except TransactionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction, account, or category not found")


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(transaction_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        await delete_transaction(db, current_user.id, transaction_id)
        await db.commit()
    except TransactionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

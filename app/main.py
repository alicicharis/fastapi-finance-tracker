from fastapi import FastAPI

from app.routers import accounts, auth, categories, transactions

app = FastAPI(title="Finance Expense Tracker")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
app.include_router(categories.router, prefix="/categories", tags=["categories"])
app.include_router(transactions.router, prefix="/transactions", tags=["transactions"])


@app.get("/health")
async def health():
    return {"status": "ok"}

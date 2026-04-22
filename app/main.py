from fastapi import FastAPI

from app.routers import accounts, auth

app = FastAPI(title="Finance Expense Tracker")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(accounts.router, prefix="/accounts", tags=["accounts"])


@app.get("/health")
async def health():
    return {"status": "ok"}

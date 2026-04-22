from fastapi import FastAPI

from app.routers import auth

app = FastAPI(title="Finance Expense Tracker")

app.include_router(auth.router, prefix="/auth", tags=["auth"])


@app.get("/health")
async def health():
    return {"status": "ok"}

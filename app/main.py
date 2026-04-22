from fastapi import FastAPI

app = FastAPI(title="Finance Expense Tracker")


@app.get("/health")
async def health():
    return {"status": "ok"}

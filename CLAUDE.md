# Finance Expense Tracker

REST API for tracking personal finances — transactions, budgets, and spending alerts.

## Stack

FastAPI · SQLAlchemy (async) · PostgreSQL · Alembic · Celery + Redis · pytest + httpx

## Structure

app/models/ — SQLAlchemy ORM models
app/routers/ — route handlers (one per feature)
app/schemas/ — Pydantic request/response models
app/services/ — business logic (routers stay thin)
app/dependencies.py — shared FastAPI dependencies
.claude/specs/ — feature specs
.claude/references/ — context files (added as features are built)

## Conventions

- Routers are thin: only request/response mapping + `Depends` wiring. All logic lives in `app/services/`.
- Services take an `AsyncSession` parameter; no global session.
- Every protected route uses `current_user: User = Depends(get_current_user)`.
- Pydantic v2 response schemas use `model_config = ConfigDict(from_attributes=True)`.

## References

- [Testing Conventions](.claude/references/testing.md) — async pytest setup, test DB isolation (SAVEPOINT pattern), `auto_error=False` gotcha

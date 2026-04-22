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

(none yet — added here after each feature is captured)

## References

(none yet — added here after each feature is captured)

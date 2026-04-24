# Feature 5: Budgets

## Why

Users need spending targets per category to know when they're on track. Transactions and categories are complete; budgets are the next unblocked P1 feature and a prerequisite for the alerts feature (Feature 7).

## What

Full CRUD for monthly budgets, with `amount_spent` and `percent_used` computed live from transactions. A `get_over_threshold` service function exposes budget utilization for the future alert job. Done when `pytest tests/test_budgets.py` passes.

## Context

**Relevant files:**

- `app/models/transaction.py` — `Transaction` ORM model; `amount` and `type` fields used for spend aggregation
- `app/models/category.py` — FK target for Budget; `user_id` nullable (defaults are shared)
- `app/routers/transactions.py` — thin router pattern to follow exactly
- `app/services/transaction.py` — service pattern: custom exceptions, `flush()` not `commit()`, typed params
- `app/schemas/transaction.py` — schema pattern: `ConfigDict(from_attributes=True)` on response, `ConfigDict(extra="forbid")` on update
- `app/main.py` — where to register the new router
- `tests/test_transactions.py` — test pattern: `_register_and_login` helper, cross-user 404 checks
- `tests/conftest.py` — DB isolation via SAVEPOINT; `async_client` fixture

**Patterns to follow:**

- Services raise typed exceptions; routers catch and return HTTP errors — see `app/services/transaction.py`
- All service functions take `(db: AsyncSession, user_id: UUID, ...)` — never access `current_user` in service layer
- `Numeric(12, 2)` for monetary amounts — never `Float`
- `await db.flush()` in service; `await db.commit()` only in router write endpoints
- Alembic migration created manually in `alembic/versions/`

**Key decisions already made:**

- `month` stored as `DATE` truncated to first of month (e.g. `2026-04-01`); unique constraint on `(user_id, category_id, month)`
- `amount_spent` computed on-the-fly by summing `expense` transactions for that category+user in that month — not denormalized
- `GET /budgets` defaults to current month; accepts optional `?month=YYYY-MM` query param
- `get_over_threshold(db, user_id, threshold)` returns budgets where `amount_spent / amount_limit >= threshold`
- Category must belong to current user or be a default (`user_id IS NULL`) — same validation as transactions

## Constraints

**Must:**

- Follow the thin-router pattern: all logic in `app/services/budget.py`
- Use `model_config = ConfigDict(from_attributes=True)` on `BudgetResponse`
- Use `model_config = ConfigDict(extra="forbid")` on `BudgetUpdate`
- `amount_spent` and `percent_used` are computed fields on `BudgetResponse` (not ORM columns)
- Enforce unique constraint on `(user_id, category_id, month)` at DB level; return 409 on violation

**Must not:**

- Add new dependencies beyond what's already in the project
- Modify existing models, routers, or services
- Denormalize `amount_spent` into the `budgets` table

**Out of scope:**

- Budget alerts / email sending (Feature 7)
- Weekly or annual budget periods
- Reports (Feature 6)

## Tasks

### T1: Budget model + Alembic migration

**Do:**

- Create `app/models/budget.py` with `Budget` ORM model: `id` (UUID PK, default `uuid4`), `user_id` (FK users, non-nullable), `category_id` (FK categories, non-nullable), `month` (`Date`, non-nullable), `amount_limit` (`Numeric(12,2)`, non-nullable), `created_at` (`DateTime(timezone=True)`)
- Add `UniqueConstraint("user_id", "category_id", "month", name="uq_budget_user_category_month")` to `__table_args__`
- Add `Budget` to `app/models/__init__.py`
- Generate migration: `alembic revision --autogenerate -m "add budgets table"` then review the file

**Files:** `app/models/budget.py`, `app/models/__init__.py`, `alembic/versions/<hash>_add_budgets_table.py`

**Verify:** `alembic upgrade head` runs without error; `\d budgets` in psql shows all columns and the unique constraint

---

### T2: Schemas + service + router

**Do:**

- Create `app/schemas/budget.py`:
  - `BudgetCreate`: `category_id UUID`, `month date` (caller passes `YYYY-MM-DD` first-of-month), `amount_limit Decimal`; validator rejects `amount_limit <= 0`
  - `BudgetUpdate`: `model_config = ConfigDict(extra="forbid")`; `amount_limit Optional[Decimal]` only (category and month cannot change)
  - `BudgetResponse`: `model_config = ConfigDict(from_attributes=True)`; all ORM fields plus `amount_spent: Decimal` and `percent_used: float`; these are populated by the service (pass them as constructor kwargs or use a classmethod factory)

- Create `app/services/budget.py`:
  - `BudgetNotFound`, `BudgetConflict` exceptions
  - `_validate_category(db, user_id, category_id)` — same logic as `transaction.py`; raises `BudgetNotFound` if not accessible
  - `_compute_spent(db, user_id, category_id, month) -> Decimal` — `func.sum` of `Transaction.amount` where `type == expense`, `category_id`, `user_id`, and date in that calendar month; returns `Decimal("0")` if no rows
  - `create_budget(db, user_id, data)` — validates category, truncates `data.month` to first of month, inserts; catches `IntegrityError` and raises `BudgetConflict`
  - `list_budgets(db, user_id, month: date) -> list[BudgetResponse]` — fetches all budgets for user+month, calls `_compute_spent` per budget, constructs `BudgetResponse` objects
  - `get_budget(db, user_id, budget_id) -> BudgetResponse` — raises `BudgetNotFound` if missing/not owned; computes spend
  - `update_budget(db, user_id, budget_id, data)` — only `amount_limit` is patchable; re-computes spend for response
  - `delete_budget(db, user_id, budget_id)` — hard delete
  - `get_over_threshold(db, user_id, threshold: float, month: date) -> list[BudgetResponse]` — returns budgets where `amount_spent / amount_limit >= threshold`

- Create `app/routers/budgets.py`: `POST /`, `GET /` (with `?month=YYYY-MM` defaulting to current month), `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`; catch `BudgetNotFound` → 404, `BudgetConflict` → 409

- Register router in `app/main.py`: `app.include_router(budgets.router, prefix="/budgets", tags=["budgets"])`

**Files:** `app/schemas/budget.py`, `app/services/budget.py`, `app/routers/budgets.py`, `app/main.py`

**Verify:** `POST /budgets/` with valid JWT and payload returns 201 with `amount_spent: "0.00"` and `percent_used: 0.0`; duplicate budget returns 409; missing auth returns 401

---

### T3: Tests

**Do:**

Create `tests/test_budgets.py` covering:

- Create returns 201 with `amount_spent` and `percent_used` fields
- Create with `amount_limit <= 0` returns 422
- Create duplicate `(category, month)` for same user returns 409
- Create with another user's category returns 404
- List returns only current user's budgets for the requested month
- List defaults to current calendar month when `?month` omitted
- `amount_spent` reflects actual expense transactions for that category+month (not income)
- `percent_used` is `amount_spent / amount_limit` (e.g. 80.0 for 80%)
- Get single — happy path and 404 for other user's budget
- Patch `amount_limit` — updated value reflected; other fields unchanged
- Delete returns 204; subsequent GET returns 404
- All write endpoints return 401 without auth

**Files:** `tests/test_budgets.py`

**Verify:** `pytest tests/test_budgets.py -v` — all tests pass

## Done

- [ ] `alembic upgrade head` — no errors
- [ ] `pytest tests/test_budgets.py -v` — all pass
- [ ] `pytest` — full suite green, no regressions
- [ ] Manual: `POST /budgets/` then `POST /transactions/` (expense, same category+month) then `GET /budgets/` — `amount_spent` updates and `percent_used` reflects correct ratio
- [ ] Manual: duplicate budget POST returns `{"detail": ...}` with 409

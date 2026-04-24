# Feature 4: Transactions

## Why

Transactions are the core data of the tracker — without them, accounts and categories are empty scaffolding. Auth, accounts, and categories are done; this is the next unblocked P0 feature.

## What

Full CRUD for transactions with filtered listing. A transaction ties a dollar amount, type (income/expense), date, description, account, and category to a user. Done when `pytest tests/test_transactions.py` passes and cross-user isolation is enforced.

## Context

**Relevant files:**

- `app/models/account.py` — Account ORM model; FK target for Transaction
- `app/models/category.py` — Category ORM model; FK target for Transaction
- `app/routers/accounts.py` — thin router pattern to follow exactly
- `app/services/account.py` — service pattern: custom exceptions, `AsyncSession` param, `flush()` not `commit()`
- `app/schemas/account.py` — schema pattern: `ConfigDict(from_attributes=True)` on response, `ConfigDict(extra="forbid")` on update
- `app/main.py` — where to register the new router
- `tests/test_accounts.py` — test pattern: `_register_and_login` helper, isolation via cross-user 404 checks

**Patterns to follow:**

- Enum columns use `values_callable=lambda x: [e.value for e in x]` — see `app/models/account.py:26`
- Services raise typed exceptions (`AccountNotFound`); routers catch and return HTTP errors
- All service functions take `(db: AsyncSession, user_id: UUID, ...)` — never access `current_user` in service layer
- Use `Numeric(12, 2)` for monetary amounts — never `Float`
- Alembic migration file created manually in `alembic/versions/`

**Key decisions already made:**

- `amount` stored as `Numeric(12,2)`; negative amounts not allowed; `type` enum carries sign semantics
- `type` enum: `income` | `expense`
- `GET /transactions` query params: `account_id`, `category_id`, `start_date`, `end_date`, `type`, `limit` (default 50), `offset`
- Account and category must belong to the current user — return 404 if not found or not owned
- No soft-delete on transactions (hard delete)

## Constraints

**Must:**

- Follow the thin-router pattern: all logic in `app/services/transaction.py`
- Use `model_config = ConfigDict(from_attributes=True)` on `TransactionResponse`
- Use `model_config = ConfigDict(extra="forbid")` on `TransactionUpdate`
- Use `await db.flush()` in service; `await db.commit()` only in router (write endpoints)
- Validate that `account_id` and `category_id` belong to `current_user` in the service layer

**Must not:**

- Add new dependencies beyond what's already in the project
- Modify existing models, routers, or services
- Use `float` for amounts

**Out of scope:**

- Bulk import/export
- Recurring transactions
- Budget spend aggregation (Feature 5)

## Tasks

### T1: Transaction model + Alembic migration

**Do:**

- Create `app/models/transaction.py` with `TransactionType` enum (`income`, `expense`) and `Transaction` ORM model: `id` (UUID PK), `user_id` (FK users), `account_id` (FK accounts), `category_id` (FK categories), `amount` (`Numeric(12,2)`), `type` (`TransactionType` enum), `date` (`Date`), `description` (`String`, nullable), `created_at` (`DateTime(timezone=True)`)
- Add `Transaction` to `app/models/__init__.py` (follow existing pattern)
- Generate Alembic migration: `alembic revision --autogenerate -m "add transactions table"` then review and clean up the generated file

**Files:** `app/models/transaction.py`, `app/models/__init__.py`, `alembic/versions/<hash>_add_transactions_table.py`

**Verify:** `alembic upgrade head` runs without error; `\d transactions` in psql shows all columns with correct types

---

### T2: Schemas + service + router

**Do:**

- Create `app/schemas/transaction.py`:
  - `TransactionCreate`: `account_id UUID`, `category_id UUID`, `amount Decimal`, `type TransactionType`, `date date`, `description Optional[str]`; validator rejects `amount <= 0`
  - `TransactionUpdate`: `ConfigDict(extra="forbid")`; all fields optional
  - `TransactionFilter`: query-param model with `account_id`, `category_id`, `start_date`, `end_date`, `type`, `limit=50`, `offset=0`
  - `TransactionResponse`: `ConfigDict(from_attributes=True)`; all fields including `id`, `user_id`, `created_at`
- Create `app/services/transaction.py`:
  - `TransactionNotFound` exception
  - `create_transaction(db, user_id, data)` — validates account and category ownership, raises 404-able exception if not found
  - `list_transactions(db, user_id, filters)` — applies all filter params; orders by `date DESC`, `created_at DESC`
  - `get_transaction(db, user_id, transaction_id)` — raises `TransactionNotFound` if missing or not owned
  - `update_transaction(db, user_id, transaction_id, data)` — uses `model_dump(exclude_unset=True)`; re-validates account/category ownership if those fields change
  - `delete_transaction(db, user_id, transaction_id)` — hard delete
- Create `app/routers/transactions.py`: `POST /`, `GET /`, `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`
- Register router in `app/main.py`: `app.include_router(transactions.router, prefix="/transactions", tags=["transactions"])`

**Files:** `app/schemas/transaction.py`, `app/services/transaction.py`, `app/routers/transactions.py`, `app/main.py`

**Verify:** `curl -X POST /transactions/` with valid JWT returns 201; invalid `amount: -5` returns 422; missing auth returns 401

---

### T3: Tests

**Do:**
Create `tests/test_transactions.py` covering:

- Create returns 201 with correct fields
- Create with `amount <= 0` returns 422
- Create with another user's `account_id` returns 404
- Create with another user's `category_id` returns 404
- List returns only current user's transactions
- List filters by `account_id`, `category_id`, `start_date`/`end_date`, `type`
- List respects `limit` and `offset`
- Get single by id — happy path and 404 for other user's transaction
- Patch partial update — untouched fields unchanged
- Patch with other user's account returns 404
- Delete returns 204; subsequent GET returns 404
- All write endpoints return 401 without auth

**Files:** `tests/test_transactions.py`

**Verify:** `pytest tests/test_transactions.py -v` — all tests pass

## Done

- [ ] `alembic upgrade head` — no errors
- [ ] `pytest tests/test_transactions.py -v` — all pass
- [ ] `pytest` — full suite green, no regressions
- [ ] Manual: `POST /transactions/` with valid payload returns 201 with `amount` as string with 2 decimal places (e.g. `"100.00"`)
- [ ] Manual: `GET /transactions/?type=expense&start_date=2026-01-01` returns filtered results

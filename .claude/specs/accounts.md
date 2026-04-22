# Accounts

## Why

Accounts are the container every transaction will hang off of (Feature 4). Without accounts, users have nothing to record spending _against_. This is P0 and the first user-scoped CRUD resource — it also locks in the per-user isolation pattern that Categories, Transactions, and Budgets will reuse.

## What

Five endpoints, all behind `get_current_user`, scoped to `current_user.id`:

- `POST /accounts` → 201 with `AccountResponse`
- `GET /accounts` → 200 list of the caller's accounts (excludes soft-deleted)
- `GET /accounts/{id}` → 200 `AccountResponse`, 404 if unknown **or** owned by another user
- `PATCH /accounts/{id}` → 200 `AccountResponse`, partial update (name, account_type, currency)
- `DELETE /accounts/{id}` → 204; sets `deleted_at` (soft delete); idempotent second call returns 404

Account fields: `id`, `user_id`, `name`, `account_type` (enum: `checking|savings|credit|cash|other`), `currency` (ISO 4217 string, default `USD`), `created_at`, `deleted_at nullable`.

Done when: pytest suite covers CRUD happy path, cross-user isolation (user B cannot see or touch user A's account), soft-delete semantics, and all routes 401 without a token.

## Context

**Relevant files:**

- `app/models/user.py` — existing `User` model; `Account.user_id` FKs here
- `app/dependencies.py:12` — `get_current_user` to inject `current_user: User` on every route
- `app/db/session.py` — `get_db` async-session dependency (use verbatim)
- `app/db/base.py` — import `Base` for the new model
- `app/routers/auth.py` — pattern reference for router shape (thin, try/except → HTTPException, `await db.commit()` in router after service flushes)
- `app/services/auth.py` — pattern reference for service shape (takes `AsyncSession`, custom exception hierarchy)
- `app/main.py` — register the new router: `app.include_router(accounts.router, prefix="/accounts", tags=["accounts"])`
- `tests/conftest.py` — reuse `db` and `async_client` fixtures; SAVEPOINT isolation already wired
- `tests/test_auth.py` — pattern reference for async httpx test structure
- `.claude/references/testing.md` — test DB quirks (SAVEPOINT requirement, `auto_error=False`)
- `alembic/versions/b70f2b32107f_users_and_refresh_tokens.py` — migration style reference

**Patterns to follow:**

- Routers thin: map HTTP ↔ service, translate service exceptions. See `app/routers/auth.py:22-51`.
- Services take `db: AsyncSession` as first arg; `db.flush()` inside service, `db.commit()` in the router.
- Service raises typed exceptions (`NotFoundError` etc.); router maps to `HTTPException`.
- Pydantic v2 response: `model_config = ConfigDict(from_attributes=True)`. See `app/schemas/auth.py:38`.
- Ownership check = query filters on `Account.user_id == current_user.id`; missing row → 404 (never 403 — don't leak existence of other users' rows).
- UUID PKs via `mapped_column(primary_key=True, default=uuid.uuid4)`. See `app/models/user.py:13`.
- Timestamps: `DateTime(timezone=True)` with `default=func.now()`. See `app/models/user.py:16`.

**Key decisions already made:**

- `account_type` is a Python `enum.Enum` mapped via SQLAlchemy `Enum(AccountType, name="account_type")` — creates a Postgres `ENUM` type. Values: `checking`, `savings`, `credit`, `cash`, `other`.
- `currency` is a plain `String(3)` (ISO 4217) with `default="USD"`. No validation against a currency table — out of scope.
- **Soft delete**: `deleted_at` nullable timestamptz. All read queries filter `deleted_at IS NULL`. Hard delete is out of scope (PRD line 86).
- `name` is not globally unique; users may have duplicate names if they want. No DB unique constraint.
- `PATCH` accepts any subset of `{name, account_type, currency}` — use `exclude_unset=True` on the schema.
- No cascade delete on the FK — `Account.user_id → users.id` uses default `ON DELETE` (restrict). Users aren't deletable via API yet, so this is moot but keeps transaction history safe later.

## Constraints

**Must:**

- Every route uses `current_user: User = Depends(get_current_user)`.
- All queries scope by `user_id = current_user.id` AND `deleted_at IS NULL` (reads).
- Return 404 — not 403 — when another user's account is referenced. Don't leak existence.
- Use `AsyncSession` throughout; no sync calls.
- Response schema must use `ConfigDict(from_attributes=True)`.
- Alembic migration generated via `uv run alembic revision --autogenerate` and inspected before commit.

**Must not:**

- No new runtime dependencies.
- Don't modify `auth.py`, `user.py`, `dependencies.py`, or `conftest.py` beyond imports.
- Don't hard-delete. Don't add a `GET /accounts?include_deleted=true` param — out of scope.
- Don't add pagination — Transactions will; Accounts won't.
- Don't refactor existing auth code.

**Out of scope:**

- Balance calculation (that's derived from Transactions — Feature 4).
- Account-to-account transfers.
- Multi-currency conversion (PRD line 247).
- Restore of soft-deleted accounts.
- Pagination / sorting params on `GET /accounts`.

## Tasks

### T1: Account model + migration

**Do:** Create `app/models/account.py`:

- `class AccountType(str, enum.Enum)` with `CHECKING = "checking"`, `SAVINGS = "savings"`, `CREDIT = "credit"`, `CASH = "cash"`, `OTHER = "other"`.
- `class Account(Base)` with `__tablename__ = "accounts"`:
  - `id: Mapped[uuid.UUID]` PK default `uuid.uuid4`
  - `user_id: Mapped[uuid.UUID]` FK→`users.id` (no ondelete), `nullable=False`, indexed
  - `name: Mapped[str]` `String`, `nullable=False`
  - `account_type: Mapped[AccountType]` `Enum(AccountType, name="account_type")`, `nullable=False`
  - `currency: Mapped[str]` `String(3)`, `nullable=False`, `default="USD"`
  - `created_at: Mapped[datetime]` `DateTime(timezone=True)`, `default=func.now()`, `nullable=False`
  - `deleted_at: Mapped[datetime | None]` `DateTime(timezone=True)`, `nullable=True`
  - `__table_args__ = (Index("ix_accounts_user_id_deleted_at", "user_id", "deleted_at"),)`
- Register model: `app/models/__init__.py` imports `Account` so Alembic autogenerate sees it.
- Generate migration: `uv run alembic revision --autogenerate -m "accounts"`. Inspect; ensure the Postgres ENUM type is created in `upgrade()` and dropped in `downgrade()`.

**Files:** `app/models/account.py`, `app/models/__init__.py` (update), `alembic/versions/<hash>_accounts.py`

**Verify:**

- `uv run alembic upgrade head` — creates `accounts` table and `account_type` enum.
- `psql $DATABASE_URL -c '\d accounts'` — shows all columns, FK to users, index on (user_id, deleted_at).
- `psql $DATABASE_URL -c '\dT+ account_type'` — shows the enum with 5 values.
- `uv run alembic downgrade -1` — drops cleanly (both table and enum).
- `uv run alembic upgrade head` — re-applies cleanly.

### T2: Schemas + service layer

**Do:** Create `app/schemas/account.py`:

- `class AccountCreate(BaseModel)`: `name: str` (min_length=1), `account_type: AccountType`, `currency: str = "USD"` (length=3, pattern=`^[A-Z]{3}$`).
- `class AccountUpdate(BaseModel)`: same three fields, all `Optional` / default `None`. Use `model_config = ConfigDict(extra="forbid")` to reject unknown fields.
- `class AccountResponse(BaseModel)`: `id: UUID`, `name: str`, `account_type: AccountType`, `currency: str`, `created_at: datetime`. `model_config = ConfigDict(from_attributes=True)`.

Create `app/services/account.py`:

- Exceptions: `class AccountError(Exception)`, `class AccountNotFound(AccountError)`.
- `async def create_account(db, user_id, data: AccountCreate) -> Account` — `db.add`, `db.flush`, return.
- `async def list_accounts(db, user_id) -> list[Account]` — `select().where(user_id=..., deleted_at is None).order_by(created_at)`.
- `async def get_account(db, user_id, account_id) -> Account` — filter by id + user_id + `deleted_at IS NULL`; raise `AccountNotFound` if missing.
- `async def update_account(db, user_id, account_id, data: AccountUpdate) -> Account` — load via `get_account`; apply `data.model_dump(exclude_unset=True)`; `db.flush`.
- `async def delete_account(db, user_id, account_id) -> None` — load via `get_account`; set `deleted_at = datetime.now(timezone.utc)`; `db.flush`. Raising `AccountNotFound` on a row that's already soft-deleted is correct (makes second DELETE return 404).

**Files:** `app/schemas/account.py`, `app/schemas/__init__.py` (update if it re-exports), `app/services/account.py`, `app/services/__init__.py` (update if it re-exports)

**Verify:**

- `uv run python -c "from app.schemas.account import AccountCreate; AccountCreate(name='X', account_type='checking')"` — exits 0.
- `uv run python -c "from app.schemas.account import AccountCreate; AccountCreate(name='X', account_type='checking', currency='usd')"` — raises (pattern fails on lowercase).
- `uv run python -c "from app.services.account import AccountNotFound, create_account, list_accounts, get_account, update_account, delete_account"` — exits 0.

### T3: Router + wire into app

**Do:** Create `app/routers/accounts.py`:

- `router = APIRouter()`
- `POST "/"` → `status_code=201`, `response_model=AccountResponse`. Body: `AccountCreate`. Calls `create_account(db, current_user.id, body)`, `await db.commit()`, returns.
- `GET "/"` → `response_model=list[AccountResponse]`. Returns `await list_accounts(db, current_user.id)`.
- `GET "/{account_id}"` → `response_model=AccountResponse`. Wraps `get_account` in try/except → 404 on `AccountNotFound`.
- `PATCH "/{account_id}"` → `response_model=AccountResponse`. `update_account` + commit; 404 on `AccountNotFound`.
- `DELETE "/{account_id}"` → `status_code=204`, returns `None`. `delete_account` + commit; 404 on `AccountNotFound`.

Every endpoint signature includes `current_user: User = Depends(get_current_user)` and `db: AsyncSession = Depends(get_db)`.

Register in `app/main.py`: `from app.routers import accounts` and `app.include_router(accounts.router, prefix="/accounts", tags=["accounts"])`.

**Files:** `app/routers/accounts.py`, `app/routers/__init__.py` (update if it re-exports), `app/main.py` (update)

**Verify:** Manual curl sequence after `uv run uvicorn app.main:app`:

```
# register + login to get $ACCESS (reuse existing auth)
curl -s -X POST :8000/accounts -H "authorization: bearer $ACCESS" -H 'content-type: application/json' \
  -d '{"name":"Chase Checking","account_type":"checking"}'
# → 201 {id, name, account_type:"checking", currency:"USD", ...}

curl -s :8000/accounts -H "authorization: bearer $ACCESS"
# → 200 [{...}]

curl -s :8000/accounts/$ID -H "authorization: bearer $ACCESS"
# → 200 {...}

curl -s -X PATCH :8000/accounts/$ID -H "authorization: bearer $ACCESS" -H 'content-type: application/json' \
  -d '{"name":"Chase Primary"}'
# → 200 {name:"Chase Primary", ...}

curl -s -X DELETE :8000/accounts/$ID -H "authorization: bearer $ACCESS" -w '%{http_code}\n'
# → 204

curl -s :8000/accounts/$ID -H "authorization: bearer $ACCESS" -w '\n%{http_code}\n'
# → 404

curl -s :8000/accounts -w '\n%{http_code}\n'
# → 401 {"detail":"Not authenticated"}
```

Also: visit `/docs` and confirm all 5 endpoints appear under the `accounts` tag with the lock icon.

### T4: Tests

**Do:** Create `tests/test_accounts.py`. Add a small helper (either inline or in the test file) to register + login and return `{Authorization: Bearer ...}` headers for a given email.

Test cases:

- `test_create_account_returns_201_with_defaults` — omitting `currency` yields `"USD"`.
- `test_create_account_requires_auth` — no token → 401.
- `test_create_account_rejects_invalid_type` — `account_type: "invalid"` → 422.
- `test_create_account_rejects_invalid_currency` — `currency: "us"` or `"USDX"` → 422.
- `test_list_accounts_returns_only_current_users` — user A creates 2, user B creates 1; each user's `GET /accounts` returns only their own.
- `test_list_accounts_excludes_soft_deleted` — create, delete, list → empty.
- `test_get_account_404_for_other_users_account` — user A creates; user B `GET /accounts/{A's id}` → 404.
- `test_patch_account_partial_update` — PATCH only `name`; `account_type` and `currency` unchanged.
- `test_patch_account_404_for_other_users_account`.
- `test_patch_account_rejects_extra_fields` — unknown field → 422 (ConfigDict extra="forbid").
- `test_delete_account_returns_204_and_is_soft` — DELETE then directly query DB via the `db` fixture to assert row still exists with `deleted_at IS NOT NULL`.
- `test_delete_account_is_idempotent_second_call_404`.
- `test_delete_account_404_for_other_users_account`.

**Files:** `tests/test_accounts.py`

**Verify:** `uv run pytest -x -v tests/test_accounts.py` — all green. `uv run pytest` — full suite green (no auth regressions).

## Done

- [ ] `uv run alembic upgrade head` applies cleanly on an empty DB (users + accounts tables both present).
- [ ] `uv run pytest` passes the new accounts tests plus all pre-existing auth tests.
- [ ] `uv run uvicorn app.main:app` boots; `/docs` shows 5 accounts endpoints under `accounts` tag, each with the auth lock.
- [ ] Manual curl sequence in T3 succeeds end-to-end; second user cannot access first user's account (404).
- [ ] Soft-delete verified via `psql -c 'select id, deleted_at from accounts'` — deleted rows still present with non-null `deleted_at`.
- [ ] No regressions: auth suite still green.

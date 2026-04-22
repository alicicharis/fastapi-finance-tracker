---
name: Testing Conventions
description: Non-obvious patterns for async pytest setup, test DB isolation, and client fixtures
type: reference
---

# Testing Conventions

## Key Decisions

- **Real PostgreSQL for tests, no SQLite or mocks**
  - **Why**: Mock/prod divergence previously masked broken migrations in comparable projects; PRD explicitly prohibits SQLite fallback.
  - **Alternatives considered**: SQLite in-memory (rejected — async dialect differences bite you), mocking DB (rejected — same reason).

- **`bcrypt` package directly, not `passlib[bcrypt]`**
  - **Why**: `passlib` is effectively unmaintained; `bcrypt` directly works fine and avoids deprecation warnings.
  - **How to apply**: Use `bcrypt.hashpw` / `bcrypt.checkpw` — see `app/services/auth.py`.

## Gotchas & Hard-Won Knowledge

- **`join_transaction_mode="create_savepoint"` is required for test isolation**
  - **Symptoms**: Without it, `AsyncSession` won't participate in the outer connection transaction, so rollback doesn't clean up test data.
  - **Root cause**: SQLAlchemy async sessions start their own transaction by default; to nest inside an existing connection transaction you must use `create_savepoint` mode.
  - **Solution**: `AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")` — see `tests/conftest.py:48`.
  - **How to avoid**: Copy the `db` fixture from `tests/conftest.py` for every new test module. Don't create a plain `AsyncSession(bind=conn)`.

- **`OAuth2PasswordBearer` must be created with `auto_error=False`**
  - **Symptoms**: FastAPI auto-returns a generic 401 before `get_current_user` runs, so the `{"detail": "Not authenticated"}` message is inconsistent and the dependency logic is bypassed.
  - **Root cause**: Default `auto_error=True` makes FastAPI raise immediately when no Bearer header is present.
  - **Solution**: `OAuth2PasswordBearer(tokenUrl=..., auto_error=False)` and check `token is None` explicitly in the dependency — see `app/dependencies.py:12`.

## Project Conventions

- Session-scoped fixture (`create_tables`) creates and drops schema once per test run via `Base.metadata.create_all/drop_all`.
- Function-scoped `db` fixture wraps each test in a transaction + SAVEPOINT that rolls back on teardown — no data bleeds between tests.
- `async_client` fixture overrides `get_db` with the test session via `app.dependency_overrides[get_db]` and clears overrides after each test.
- Use `DATABASE_URL_TEST` env var for the test database URL — must be set before running `pytest`.

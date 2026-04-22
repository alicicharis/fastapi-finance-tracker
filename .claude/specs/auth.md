# Auth

## Why

Every feature in the PRD depends on an authenticated user. Without registration, login, and a `get_current_user` dependency, no other endpoint can be scoped per-user. This is P0 and blocks Features 2–7.

## What

Three public endpoints plus a reusable FastAPI dependency:

- `POST /auth/register` → 201 with `{id, email}`, 409 on duplicate email
- `POST /auth/login` → 200 with `{access_token, refresh_token, token_type}`, 401 on bad credentials
- `POST /auth/refresh` → 200 with a new access + refresh token (rotating, single-use)
- `get_current_user` dependency validates a Bearer JWT and returns the `User` ORM object, 401 otherwise

Access token TTL 15 min, refresh token TTL 7 days. Refresh tokens are persisted so they can be revoked; each refresh rotates the token. Passwords hashed with bcrypt.

Done when: all acceptance criteria in PRD Feature 1 pass, and the pytest suite exercises register → login → protected-route → refresh → re-use-old-refresh-token-rejected.

## Context

**Relevant files (all new — greenfield):**

- `pyproject.toml` — add deps (`fastapi`, `uvicorn`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `passlib[bcrypt]`, `python-jose[cryptography]`, `pytest`, `pytest-asyncio`, `httpx`)
- `app/__init__.py`, `app/main.py` — FastAPI app entrypoint, mount auth router
- `app/config.py` — `Settings` via `pydantic-settings` (`DATABASE_URL`, `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_TTL_MIN`, `REFRESH_TOKEN_TTL_DAYS`)
- `app/db/session.py` — async engine + `AsyncSession` factory + `get_db` dependency
- `app/db/base.py` — declarative `Base`
- `app/models/user.py` — `User(id, email UNIQUE, hashed_password, created_at)`
- `app/models/refresh_token.py` — `RefreshToken(id, user_id FK, token_hash UNIQUE, expires_at, revoked_at nullable, created_at)`
- `app/schemas/auth.py` — `RegisterRequest`, `LoginRequest`, `TokenResponse`, `RefreshRequest`, `UserResponse`
- `app/services/auth.py` — `hash_password`, `verify_password`, `create_access_token`, `create_refresh_token`, `rotate_refresh_token`, `decode_access_token`, `authenticate_user`, `register_user`
- `app/routers/auth.py` — the three endpoints, thin — delegate to service
- `app/dependencies.py` — `get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db))`
- `alembic/` — env.py (async), versions/<hash>\_users_refresh_tokens.py
- `alembic.ini`
- `tests/conftest.py` — test DB setup, `async_client` fixture, transaction-rollback-per-test
- `tests/test_auth.py` — register/login/refresh/protected-route cases

**Patterns to establish (this feature seeds them):**

- Routers thin: only request/response mapping + dependency wiring. All logic in `app/services/`.
- Services take an `AsyncSession` parameter; no global session.
- Pydantic v2 schemas with `model_config = ConfigDict(from_attributes=True)` on response models.
- Every protected route takes `current_user: User = Depends(get_current_user)`.
- Tests: `httpx.AsyncClient(transport=ASGITransport(app=app))`, not the TestClient.

**Key decisions already made (from PRD + plan):**

- `python-jose[cryptography]` for JWT (not PyJWT).
- `passlib[bcrypt]` for hashing.
- Refresh tokens: store **sha256 hash** of the opaque random token in DB (not the token itself). Rotation = mark old row `revoked_at=now()`, insert new row.
- Refresh token is an opaque secret (`secrets.token_urlsafe(32)`), not a JWT. Simpler and avoids double-signing.
- Access token payload: `{sub: user_id, exp, iat}`.
- `JWT_SECRET` read from env; fail fast if missing in non-test env.
- Alembic `env.py` uses async engine + `connection.run_sync(do_migrations)`.
- Tests run against a real PostgreSQL test DB (`DATABASE_URL_TEST` env var). No SQLite, no mocking the DB — matches PRD's testing philosophy.
- Each test function wraps in a SAVEPOINT that's rolled back on teardown.

## Constraints

**Must:**

- Follow the `app/{models,routers,schemas,services}` layout from CLAUDE.md.
- All DB calls async (`AsyncSession`).
- Use `Depends(get_current_user)` on every non-auth route going forward (set the precedent here).
- Return `{detail: "..."}` on error (FastAPI default / RFC 7807-style, per PRD Architecture Decisions).
- Hash passwords with bcrypt; never store plaintext.
- Store only refresh token **hashes** in DB.

**Must not:**

- No SQLite fallback; tests require PostgreSQL.
- No sync SQLAlchemy sessions anywhere.
- Don't bake admin/role concepts — PRD has none.
- Don't add email verification or password reset — out of scope for Feature 1.
- No OAuth providers.

**Out of scope:**

- Accounts, categories, transactions, budgets, reports, alerts (Features 2–7).
- Rate limiting, account lockout, MFA.
- Password reset flow.
- User profile updates.

## Tasks

### T1: Project scaffolding

**Do:** Add dependencies to `pyproject.toml`. Create `app/__init__.py`, `app/main.py` (FastAPI app, health endpoint `GET /health` returning `{status: "ok"}`), `app/config.py` (`Settings` with fields above, loads from env / `.env`), `app/db/base.py` (declarative `Base`), `app/db/session.py` (async engine from `DATABASE_URL`, `async_session_maker`, `get_db` async generator dependency). Run `alembic init -t async alembic`; wire `alembic/env.py` to import `Base` and use `settings.DATABASE_URL`. Update `.gitignore` if needed (`.env`).

**Files:** `pyproject.toml`, `app/__init__.py`, `app/main.py`, `app/config.py`, `app/db/base.py`, `app/db/session.py`, `app/db/__init__.py`, `alembic/env.py`, `alembic/script.py.mako`, `alembic.ini`, `.env.example`

**Verify:** `uv sync` installs clean. `uv run uvicorn app.main:app` boots; `curl localhost:8000/health` returns `{"status":"ok"}`. `uv run alembic current` runs without error against a local Postgres.

### T2: User + RefreshToken models and initial migration

**Do:** Create `app/models/__init__.py`, `app/models/user.py` (`User`: `id` uuid PK, `email` str UNIQUE NOT NULL, `hashed_password` str NOT NULL, `created_at` timestamptz default now()). Create `app/models/refresh_token.py` (`RefreshToken`: `id` uuid PK, `user_id` uuid FK→users.id ON DELETE CASCADE, `token_hash` str UNIQUE NOT NULL, `expires_at` timestamptz NOT NULL, `revoked_at` timestamptz nullable, `created_at` timestamptz default now(); index on `(user_id, revoked_at)`). Generate Alembic revision `uv run alembic revision --autogenerate -m "users and refresh_tokens"`. Inspect + commit the migration.

**Files:** `app/models/__init__.py`, `app/models/user.py`, `app/models/refresh_token.py`, `alembic/versions/<hash>_users_and_refresh_tokens.py`

**Verify:** `uv run alembic upgrade head` creates both tables. `psql \d users` shows expected columns + unique on email. `psql \d refresh_tokens` shows FK and unique on token_hash. `uv run alembic downgrade base` cleanly drops both.

### T3: Auth service + schemas

**Do:** Create `app/schemas/__init__.py`, `app/schemas/auth.py` with:

- `RegisterRequest(email: EmailStr, password: str)` — password `min_length=8`
- `LoginRequest(email: EmailStr, password: str)`
- `RefreshRequest(refresh_token: str)`
- `TokenResponse(access_token: str, refresh_token: str, token_type: Literal["bearer"] = "bearer")`
- `UserResponse(id: UUID, email: EmailStr)` with `from_attributes=True`

Create `app/services/__init__.py`, `app/services/auth.py` with:

- `hash_password(plain: str) -> str` — passlib bcrypt
- `verify_password(plain: str, hashed: str) -> bool`
- `create_access_token(user_id: UUID) -> str` — jose JWT, 15-min exp
- `decode_access_token(token: str) -> UUID` — raises `InvalidToken` on bad/expired
- `_hash_refresh(token: str) -> str` — sha256 hex
- `issue_refresh_token(db, user_id) -> tuple[str, RefreshToken]` — generate `secrets.token_urlsafe(32)`, insert hashed row with 7-day expiry, return (plain, row)
- `rotate_refresh_token(db, plain_token: str) -> tuple[User, str, str]` — look up by hash, ensure not revoked/expired, mark revoked, issue new access+refresh, return `(user, access, refresh)`. Raises on invalid/expired/revoked.
- `register_user(db, email, password) -> User` — raises `DuplicateEmail` if email exists
- `authenticate_user(db, email, password) -> User | None`

Define a small exception hierarchy in `app/services/auth.py` (`AuthError`, `InvalidCredentials`, `DuplicateEmail`, `InvalidToken`) — routers map these to HTTP status codes.

**Files:** `app/schemas/__init__.py`, `app/schemas/auth.py`, `app/services/__init__.py`, `app/services/auth.py`

**Verify:** `uv run python -c "from app.services.auth import hash_password, verify_password; h=hash_password('x'); assert verify_password('x', h) and not verify_password('y', h)"` exits 0. Import-check: `uv run python -c "from app.services import auth; print(dir(auth))"` lists expected symbols.

### T4: Auth router + `get_current_user` dependency

**Do:** Create `app/routers/__init__.py`, `app/routers/auth.py` with the three endpoints; each calls the service and translates service exceptions to `HTTPException(status_code=…)`.

- `POST /auth/register` → `status_code=201`, returns `UserResponse`
- `POST /auth/login` → `200`, returns `TokenResponse`
- `POST /auth/refresh` → `200`, returns `TokenResponse`

Create `app/dependencies.py` with:

- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)`
- `async def get_current_user(token, db) -> User` — decodes access token, loads user, raises `401 {detail: "Not authenticated"}` on any failure.

Register the router in `app/main.py` via `app.include_router(auth.router, prefix="/auth", tags=["auth"])`. Add a protected route `GET /auth/me` that returns `UserResponse(current_user)` to exercise the dependency (useful for clients; stays).

**Files:** `app/routers/__init__.py`, `app/routers/auth.py`, `app/dependencies.py`, `app/main.py` (update)

**Verify:** Manual end-to-end with `curl`:

```
curl -s -X POST :8000/auth/register -H 'content-type: application/json' -d '{"email":"a@b.com","password":"password123"}'
# → 201 {id, email}

curl -s -X POST :8000/auth/login -H 'content-type: application/json' -d '{"email":"a@b.com","password":"password123"}'
# → 200 {access_token, refresh_token, token_type:"bearer"}

curl -s :8000/auth/me -H "authorization: bearer $ACCESS"
# → 200 {id, email}

curl -s :8000/auth/me
# → 401 {"detail":"Not authenticated"}

curl -s -X POST :8000/auth/refresh -H 'content-type: application/json' -d "{\"refresh_token\":\"$REFRESH\"}"
# → 200 new tokens; re-using the same $REFRESH now returns 401
```

### T5: Tests

**Do:** Create `tests/__init__.py`, `tests/conftest.py`:

- session-scoped fixture creates schema on test DB (`DATABASE_URL_TEST`) via `Base.metadata.create_all` OR `alembic upgrade head`
- function-scoped `db` fixture opens a connection + begins a transaction + binds `AsyncSession` to it + rolls back on teardown
- `async_client` fixture overrides `get_db` to return the test session, wraps app in `ASGITransport`

Create `tests/test_auth.py`:

- `test_register_returns_201_and_user`
- `test_register_duplicate_email_returns_409`
- `test_register_weak_password_returns_422`
- `test_login_success_returns_tokens`
- `test_login_wrong_password_returns_401`
- `test_login_unknown_email_returns_401`
- `test_protected_route_requires_token`
- `test_protected_route_accepts_valid_token`
- `test_protected_route_rejects_expired_token` (monkeypatch `ACCESS_TOKEN_TTL_MIN` to a tiny value OR craft a manually-expired JWT with jose)
- `test_refresh_rotates_and_old_token_is_rejected`
- `test_refresh_with_invalid_token_returns_401`

**Files:** `tests/__init__.py`, `tests/conftest.py`, `tests/test_auth.py`

**Verify:** `uv run pytest -x -v tests/test_auth.py` — all green.

## Done

- [ ] `uv run pytest` passes 11/11 auth tests
- [ ] `uv run alembic upgrade head` applies cleanly on an empty DB
- [ ] `uv run uvicorn app.main:app` boots; OpenAPI at `/docs` shows the four endpoints (`register`, `login`, `refresh`, `me`)
- [ ] Manual curl sequence in T4 succeeds end-to-end
- [ ] `get_current_user` is importable from `app.dependencies` and ready to be used by Feature 2 (Accounts)
- [ ] No plaintext passwords or plaintext refresh tokens land in the DB (confirm via `psql -c 'select hashed_password, token_hash from users, refresh_tokens limit 1'`)

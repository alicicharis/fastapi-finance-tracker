# Product Requirements Document

## Vision

A personal finance REST API that lets individuals track income and spending across manual accounts, categorize transactions, set monthly budgets, and receive proactive email alerts — all through a clean, authenticated HTTP interface.

## Problem Statement

People who want to understand their spending patterns have two options: heavyweight apps that require bank integrations, or spreadsheets that require manual upkeep with no automation. Neither is ideal for developers or privacy-conscious users who want a self-hosted, programmable solution. The core problems are:

- No easy way to record and categorize transactions without connecting a bank
- Budgets exist in spreadsheets but never trigger alerts before they're blown
- No programmatic access to spending summaries for custom dashboards or scripts

## Solution Overview

A FastAPI backend exposing a JSON REST API. Users register and authenticate with JWTs. They create manual accounts, record transactions against those accounts and categories, define monthly budgets per category, query spending reports, and receive email alerts via a Celery background job when a budget category reaches 80% utilization.

## User Stories

1. As a user, I want to register with an email and password so that I can have my own isolated data.
2. As a user, I want to log in and receive a JWT so that I can authenticate subsequent requests.
3. As a user, I want to refresh my access token so that I stay logged in without re-entering credentials.
4. As a user, I want to create a manual bank account (e.g. "Chase Checking") so that I can track money across multiple accounts.
5. As a user, I want to list, update, and delete my accounts so that I can keep my account list accurate.
6. As a user, I want to record a transaction with an amount, date, description, account, and category so that I can build a spending history.
7. As a user, I want to list transactions with filters (date range, account, category) so that I can review my history.
8. As a user, I want to update and delete transactions so that I can correct mistakes.
9. As a user, I want a set of default categories (Food, Transport, Housing, etc.) available on sign-up so that I can start recording immediately.
10. As a user, I want to create custom categories so that I can model my personal spending structure.
11. As a user, I want to list, update, and delete my custom categories so that I can keep them tidy.
12. As a user, I want to set a monthly budget for a category so that I have a spending target.
13. As a user, I want to update or delete a budget so that I can adjust targets over time.
14. As a user, I want to list all my budgets with current spend so that I can see where I stand this month.
15. As a user, I want a spending-by-category report for any date range so that I can understand where my money goes.
16. As a user, I want a month-over-month summary report so that I can see spending trends across months.
17. As a user, I want an email alert when any budget category reaches 80% of its monthly limit so that I can course-correct before overspending.
18. As a user, I want alerts to fire automatically in the background so that I don't have to check manually.

## Feature Roadmap

### Feature 1: Auth

- **Status**: `planned`
- **Priority**: P0
- **Depends on**: none
- **Description**: Users register with email + password, log in to receive a short-lived access token and a longer-lived refresh token, and use the access token as a Bearer header on all subsequent requests.
- **Modules**:
  - `app/models/user.py` — `User` ORM model (id, email, hashed_password, created_at)
  - `app/schemas/auth.py` — `RegisterRequest`, `LoginRequest`, `TokenResponse`, `RefreshRequest`
  - `app/services/auth.py` — password hashing (bcrypt), JWT encode/decode, token refresh logic
  - `app/routers/auth.py` — `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`
  - `app/dependencies.py` — `get_current_user` dependency that validates Bearer JWT and returns the User
- **Implementation decisions**:
  - Use `python-jose` or `PyJWT` for JWT; store `user_id` and `exp` in payload.
  - Access token TTL: 15 min. Refresh token TTL: 7 days, stored in DB (`refresh_tokens` table) so they can be revoked.
  - Passwords hashed with `bcrypt` via `passlib`.
  - Email must be unique; return 409 on duplicate register.
  - Refresh tokens are single-use: each refresh rotates the token (old one invalidated, new one issued). More secure and acceptable since this is an API-first product without concurrent-tab UX concerns.
  - Alembic migration: `users` table, `refresh_tokens` table.
- **Testing approach**:
  - Use `pytest` + `httpx` `AsyncClient` against a test PostgreSQL database.
  - Test: successful register, duplicate email 409, login with bad password 401, valid token accepted by protected route, expired token rejected, refresh flow.
- **Acceptance criteria**:
  - `POST /auth/register` returns 201 with user id and email.
  - `POST /auth/login` returns access + refresh tokens.
  - `POST /auth/refresh` exchanges a valid refresh token for a new access token.
  - All other endpoints return 401 when no or invalid token is provided.

---

### Feature 2: Accounts

- **Status**: `planned`
- **Priority**: P0
- **Depends on**: Feature 1 (Auth)
- **Description**: Users create named manual accounts (e.g. "Chase Checking", "Amex Card") and manage them. Each account belongs to one user.
- **Modules**:
  - `app/models/account.py` — `Account` ORM model (id, user_id FK, name, account_type, currency, created_at)
  - `app/schemas/account.py` — `AccountCreate`, `AccountUpdate`, `AccountResponse`
  - `app/services/account.py` — CRUD operations scoped to the current user
  - `app/routers/accounts.py` — `POST /accounts`, `GET /accounts`, `GET /accounts/{id}`, `PATCH /accounts/{id}`, `DELETE /accounts/{id}`
- **Implementation decisions**:
  - `account_type` is a string enum: `checking`, `savings`, `credit`, `cash`, `other`.
  - `currency` defaults to `USD`; stored as ISO 4217 string.
  - Deleting an account soft-deletes (sets `deleted_at`) to preserve transaction history integrity; hard-delete is out of scope.
  - All queries filter by `user_id` from the JWT — users cannot see each other's accounts.
  - Alembic migration: `accounts` table.
- **Testing approach**:
  - CRUD happy paths, 404 on unknown id, 403/404 if user tries to access another user's account.
- **Acceptance criteria**:
  - Full CRUD works; listing returns only the authenticated user's accounts.
  - Deleting an account does not cascade-delete transactions (soft-delete).

---

### Feature 3: Categories

- **Status**: `planned`
- **Priority**: P0
- **Depends on**: Feature 1 (Auth)
- **Description**: A set of system-wide default categories is seeded at startup. Users can also create custom categories. Categories are used to label transactions and budgets.
- **Modules**:
  - `app/models/category.py` — `Category` ORM model (id, user_id nullable FK, name, is_default, created_at)
  - `app/schemas/category.py` — `CategoryCreate`, `CategoryUpdate`, `CategoryResponse`
  - `app/services/category.py` — list (defaults + user's own), create, update, delete
  - `app/routers/categories.py` — `GET /categories`, `POST /categories`, `PATCH /categories/{id}`, `DELETE /categories/{id}`
  - `app/db/seed.py` — seed script for default categories
- **Implementation decisions**:
  - Default categories have `user_id = NULL` and `is_default = TRUE`. Users cannot edit or delete defaults.
  - `GET /categories` returns defaults union user-created categories for the current user.
  - Custom category names must be unique per user (case-insensitive).
  - Deleting a category that has existing transactions returns 409. Transactions must be re-categorized or deleted first. This preserves data integrity and avoids silent uncategorized transactions corrupting reports and budgets.
  - Alembic migration: `categories` table + seed data via migration or startup event.
- **Testing approach**:
  - Defaults appear for all users; user-created categories are isolated; cannot delete a default; duplicate name returns 409.
- **Acceptance criteria**:
  - Default categories available immediately after registration with no extra setup.
  - Users can create, rename, and delete their own categories.
  - Deleting a category that has transactions returns 409 (constraint protection).

---

### Feature 4: Transactions

- **Status**: `planned`
- **Priority**: P0
- **Depends on**: Feature 2 (Accounts), Feature 3 (Categories)
- **Description**: Core feature. Users record individual financial transactions — a debit or credit — tied to an account and a category.
- **Modules**:
  - `app/models/transaction.py` — `Transaction` ORM model (id, user_id FK, account_id FK, category_id FK, amount, type enum, date, description, created_at)
  - `app/schemas/transaction.py` — `TransactionCreate`, `TransactionUpdate`, `TransactionResponse`, `TransactionFilter`
  - `app/services/transaction.py` — CRUD + filtered list query
  - `app/routers/transactions.py` — `POST /transactions`, `GET /transactions`, `GET /transactions/{id}`, `PATCH /transactions/{id}`, `DELETE /transactions/{id}`
- **Implementation decisions**:
  - `amount` stored as `Numeric(12,2)` — never float.
  - `type` enum: `income` | `expense`. Negative amounts not allowed; type carries the sign semantics.
  - `GET /transactions` supports query params: `account_id`, `category_id`, `start_date`, `end_date`, `type`, `limit` (default 50), `offset`.
  - Account and category must belong to the current user (validate in service layer, 404 if not found/owned).
  - Alembic migration: `transactions` table.
- **Testing approach**:
  - Create/read/update/delete; filter by each param; cross-user isolation; invalid account/category returns 404.
- **Acceptance criteria**:
  - Transactions are filterable by date range, account, and category.
  - Amount stored and returned with 2 decimal precision.
  - User cannot create a transaction against another user's account or category.

---

### Feature 5: Budgets

- **Status**: `planned`
- **Priority**: P1
- **Depends on**: Feature 3 (Categories), Feature 4 (Transactions)
- **Description**: Users define a monthly spending limit per category. The budget list endpoint shows each budget alongside the amount spent so far in the current calendar month.
- **Modules**:
  - `app/models/budget.py` — `Budget` ORM model (id, user_id FK, category_id FK, month date, amount_limit Numeric, created_at)
  - `app/schemas/budget.py` — `BudgetCreate`, `BudgetUpdate`, `BudgetResponse` (includes `amount_spent`, `percent_used`)
  - `app/services/budget.py` — CRUD + spend aggregation query, `get_over_threshold(user_id, threshold)` for alerts
  - `app/routers/budgets.py` — `POST /budgets`, `GET /budgets`, `GET /budgets/{id}`, `PATCH /budgets/{id}`, `DELETE /budgets/{id}`
- **Implementation decisions**:
  - `month` stored as `DATE` truncated to first of the month (e.g. `2026-04-01`). One budget per user+category+month (unique constraint).
  - `amount_spent` is computed on-the-fly by summing `expense` transactions for the category in that month — not denormalized.
  - `GET /budgets` defaults to current month; accepts optional `?month=YYYY-MM` query param.
  - `get_over_threshold` returns budgets where `amount_spent / amount_limit >= threshold` — used by the alert job.
  - Alembic migration: `budgets` table.
- **Testing approach**:
  - Budget CRUD; spend computation matches transaction sum; `percent_used` accurate; unique constraint enforced; `get_over_threshold` returns correct rows.
- **Acceptance criteria**:
  - `GET /budgets` response includes `amount_spent` and `percent_used` computed from transactions.
  - Cannot create duplicate budget for same user+category+month.

---

### Feature 6: Reports

- **Status**: `planned`
- **Priority**: P1
- **Depends on**: Feature 4 (Transactions), Feature 3 (Categories)
- **Description**: Two read-only reporting endpoints: spending broken down by category for a date range, and a month-over-month summary comparing total spending across recent months.
- **Modules**:
  - `app/services/reports.py` — `spending_by_category(user_id, start, end)`, `month_over_month(user_id, months=6)`
  - `app/schemas/report.py` — `CategorySpendRow`, `SpendingByCategoryResponse`, `MonthSummary`, `MonthOverMonthResponse`
  - `app/routers/reports.py` — `GET /reports/spending-by-category`, `GET /reports/month-over-month`
- **Implementation decisions**:
  - Both endpoints are read-only; no writes.
  - `spending_by_category`: params `start_date`, `end_date` (required). Returns list of `{category_id, category_name, total_expense, total_income, net}`.
  - `month_over_month`: param `months` (default 6, max 24). Returns list of `{month, total_expense, total_income, net}` ordered oldest-first.
  - Queries use SQLAlchemy `func.sum` + `group_by` — single DB round-trip each.
  - Only `expense` transactions counted toward spending; `income` reported separately.
- **Testing approach**:
  - Known transaction fixtures; assert aggregate values; empty range returns empty list; months with no transactions appear as zero-rows.
- **Acceptance criteria**:
  - Spending-by-category sums match sum of matching transactions.
  - Month-over-month returns one row per calendar month in the requested range, including zero-spend months.

---

### Feature 7: Alerts

- **Status**: `planned`
- **Priority**: P1
- **Depends on**: Feature 5 (Budgets)
- **Description**: A Celery background task runs on a schedule (daily, configurable) and emails users when any of their budgets have reached 80% of the monthly limit.
- **Modules**:
  - `app/workers/celery_app.py` — Celery app instance, Redis broker config, beat schedule
  - `app/workers/tasks.py` — `check_budget_alerts()` task: fetches all users, calls `budget.get_over_threshold`, checks `budget_alerts` for today's date, sends email, records sent alert
  - `app/models/budget_alert.py` — `BudgetAlert` ORM model (id, user_id FK, budget_id FK, sent_date date); unique constraint on (budget_id, sent_date)
  - `app/services/email.py` — `send_budget_alert(user_email, budget_summary)` using SMTP (configurable via env vars); thin wrapper so tests can mock it
  - `app/config.py` — `Settings` (pydantic-settings): `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_FROM_EMAIL`, `ALERT_THRESHOLD` (default 0.8)
- **Implementation decisions**:
  - Celery beat triggers `check_budget_alerts` once per day at 08:00 UTC.
  - The task queries all users with at least one budget at or above threshold for the current month.
  - One email per user (not per budget) with a table of all over-threshold budgets.
  - Alerts are de-duped per day: a `budget_alerts` table records `(user_id, budget_id, sent_date)`. The task skips any budget that already has a record for today's date, preventing repeat emails on the same calendar day.
  - SMTP credentials from environment; `smtplib` or `aiosmtplib` for sending.
  - Alembic migration: `budget_alerts` table.
- **Testing approach**:
  - Unit-test `check_budget_alerts` with a mocked `send_budget_alert` and seeded budgets/transactions.
  - Test threshold boundary: 79% does not trigger, 80% does.
  - Test `send_budget_alert` in isolation with a mock SMTP server (e.g. `aiosmtpd` or `unittest.mock`).
- **Acceptance criteria**:
  - Celery task runs without error and calls `send_budget_alert` for each user with a qualifying budget.
  - Email contains the category name, budget limit, amount spent, and percent used.
  - Task does not raise if a user has no email or no over-threshold budgets.
  - A budget that already triggered an alert today does not send a second email; re-running the task on the same day is idempotent.

---

## Architecture Decisions

- **Framework**: FastAPI with `asyncio` throughout — all DB calls use `asyncpg` via SQLAlchemy async sessions.
- **ORM**: SQLAlchemy 2.x declarative models; `AsyncSession` passed via FastAPI dependency injection.
- **Migrations**: Alembic with `async` env setup; migrations run on startup in development, manually in production.
- **Auth**: Stateless JWT access tokens + DB-backed refresh tokens. `get_current_user` dependency injected into all protected routes.
- **Background jobs**: Celery with Redis as both broker and result backend. Beat scheduler for the daily alert job.
- **Config**: `pydantic-settings` `Settings` singleton loaded from environment variables / `.env` file.
- **Testing**: `pytest-asyncio` + `httpx.AsyncClient` against a real test PostgreSQL database (no mocking the DB layer). Each test gets a fresh transaction that is rolled back after the test.
- **Error handling**: FastAPI exception handlers return RFC 7807-style `{detail: ...}` JSON. Validation errors use FastAPI's default 422 shape.
- **API versioning**: No versioning prefix in v1; add `/v1/` if/when breaking changes are needed.

## Out of Scope

- Plaid or any other bank integration
- Frontend or mobile application
- Mobile push notifications
- Multi-currency conversion
- Recurring transactions
- Shared/joint accounts
- Export to CSV/PDF
- OAuth (Google, GitHub) login

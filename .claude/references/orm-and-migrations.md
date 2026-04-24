---
name: ORM and Migrations
description: Non-obvious SQLAlchemy/Alembic quirks hit while building this project — Postgres ENUM value mapping, autogen drift
type: reference
---

# ORM and Migrations

## Gotchas & Hard-Won Knowledge

- **`values_callable` is required when mapping a Python `enum.Enum` to a Postgres ENUM if you want the ENUM to contain lowercase `.value`s**
  - **Symptoms**: Without it, Postgres stores (and the API round-trips) the Python member *name* — e.g. `"CHECKING"` — instead of the intended `"checking"`. Tests asserting `account_type == "checking"` fail with the uppercase form; the enum type in `\dT+` lists `CHECKING, SAVINGS, …` rather than the values declared in Python.
  - **Root cause**: SQLAlchemy's `Enum` type defaults to using the Python member *name* as the DB literal. Our enums are declared `class AccountType(str, enum.Enum): CHECKING = "checking"` — the `.value` is lowercase but the `.name` is uppercase. `Enum(AccountType, …)` with no `values_callable` binds `.name`.
  - **Solution**: `Enum(AccountType, name="account_type", values_callable=lambda x: [e.value for e in x])` — see `app/models/account.py:26`.
  - **How to avoid**: Every time you add a Python enum that maps to a Postgres ENUM (Transaction.type, BudgetAlert status, etc.), include `values_callable`. If you forget, the autogen migration will bake the wrong labels into the Postgres type and you'll need a new migration to alter the ENUM.

- **Alembic autogen picks up *any* drift between the current model and the live DB — including rows added by older migrations**
  - **Symptoms**: A new migration (e.g. `7b6cb1ade18f_accounts.py`) contains `op.alter_column` calls on tables you didn't touch (`refresh_tokens`, `users`), changing `TIMESTAMP` → `TIMESTAMP WITH TIME ZONE`.
  - **Root cause**: The initial auth migration wrote those columns as plain `TIMESTAMP`, but the ORM models declare `DateTime(timezone=True)`. Autogen diffs model-vs-DB every run, so unrelated drift surfaces in whichever migration you happen to generate next.
  - **Solution**: Accept the bundled alter (the model is the source of truth and `DateTime(timezone=True)` is what we want) OR fix the prior migration and re-baseline. We accepted it.
  - **How to avoid**: Inspect every autogen diff for columns outside the feature you're building. If they're legitimate drift fixes, keep them; if they're noise (e.g. index renaming from a SQLAlchemy version upgrade), delete them before committing.

- **Partial functional unique indexes are not generated correctly by Alembic autogen**
  - **Symptoms**: Autogen produces plain `op.create_index(...)` without `postgresql_where=` or functional column expressions. The partial constraint is silently missing from the migration.
  - **Root cause**: Alembic autogen doesn't emit `postgresql_where` or `func.lower()` expressions; it only sees the index exists in the model and emits a simplified version.
  - **Solution**: Hand-edit the migration. Use `sa.literal_column('lower(name)')` for functional index columns and `postgresql_where=sa.text("user_id IS NOT NULL")` for the partial clause. See `alembic/versions/a4531730c143_categories.py:36–37`.
  - **How to avoid**: After any `alembic revision --autogenerate`, inspect the generated file for indexes that use `func.lower()` or `postgresql_where` in the model's `__table_args__` — always hand-edit those.

- **Seeding lookup data: use a single sync helper callable by both Alembic and test setup**
  - **Pattern used**: `app/db/seed.py` exports `DEFAULT_CATEGORIES` (the canonical list) and `seed_default_categories(connection)` (a sync function using raw SQL with `ON CONFLICT DO NOTHING`). The Alembic migration imports `DEFAULT_CATEGORIES` for `op.bulk_insert`; `tests/conftest.py` calls `await conn.run_sync(seed_default_categories)` after `create_all`.
  - **Why**: Having two definitions of the default list causes drift. One source of truth keeps migration and tests in sync.
  - **How to apply**: When any feature needs seeded lookup rows, put the canonical list and seed helper in `app/db/seed.py`. Use `op.bulk_insert` in the migration (idempotent via `ON CONFLICT DO NOTHING`), and `conn.run_sync(seed_fn)` in `tests/conftest.py:create_tables`.

## Project Conventions

- Enum columns use SQLAlchemy `Enum(PyEnum, name="<snake_case_type_name>", values_callable=lambda x: [e.value for e in x])`. The `name=` is the Postgres type name and must be stable across migrations — renaming it requires a `CREATE TYPE … RENAME` migration.
- Timestamps are always `DateTime(timezone=True)` with `default=func.now()`. Don't use naive `DateTime`.
- UUID PKs via `mapped_column(primary_key=True, default=uuid.uuid4)`. No sequences.
- Soft-deletable tables carry `deleted_at: Mapped[datetime | None]` and an index on `(user_id, deleted_at)`; read queries filter `deleted_at IS NULL`. Used by `accounts` — extend the pattern to other user-scoped resources when soft-delete is a requirement.
- Default/shared categories (user_id IS NULL) are valid FK targets for user-owned records (transactions). Ownership validation must allow `OR user_id IS NULL` when checking category ownership — see `app/services/transaction.py:_validate_category`.

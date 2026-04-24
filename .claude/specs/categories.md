# Categories

## Why

Categories are the label every transaction and every budget will attach to (Features 4 and 5). Without them, a transaction can't be recorded and a budget has nothing to target. This is P0 and the last schema building block before Transactions land.

## What

Four endpoints, all behind `get_current_user`:

- `POST /categories` → 201 with `CategoryResponse` (custom category for the caller); 409 on duplicate name (case-insensitive, per user)
- `GET /categories` → 200 list of system defaults + the caller's own custom categories
- `PATCH /categories/{id}` → 200 `CategoryResponse`; partial update of `name`; 403 if target is a default; 404 if unknown or owned by another user
- `DELETE /categories/{id}` → 204; 403 if target is a default; 404 if unknown or owned by another user

Category fields: `id`, `user_id` (nullable UUID — `NULL` for defaults), `name`, `is_default` (bool), `created_at`.

Default categories (seeded once): **Food, Transport, Housing, Utilities, Healthcare, Entertainment, Shopping, Other**. Every registered user sees them immediately via `GET /categories` — no per-user copy is made.

Done when: pytest suite covers defaults visible to every user, custom-category CRUD, cross-user isolation, 403 on default edits, 409 on duplicate-name create, and the seed is present after `uv run alembic upgrade head` on an empty DB.

## Context

**Relevant files:**

- `app/models/user.py` — `User` model; `Category.user_id` FKs here (nullable)
- `app/models/account.py` — closest existing pattern for a user-scoped model (enum, index, timestamps)
- `app/dependencies.py:12` — `get_current_user` dependency
- `app/db/session.py` — `get_db` async-session dependency
- `app/db/base.py` — `Base` to import for the new model
- `app/routers/accounts.py` — router shape to mirror (thin, service exceptions → `HTTPException`, `await db.commit()` in router)
- `app/services/account.py` — service shape to mirror (`AsyncSession` first arg, typed exception hierarchy, `db.flush()` inside service)
- `app/schemas/account.py` — schema shape to mirror (Pydantic v2, `ConfigDict(from_attributes=True)`, `extra="forbid"` on update)
- `app/main.py` — register the new router
- `tests/conftest.py` — the `create_tables` session fixture needs to also seed defaults (see T1)
- `tests/test_accounts.py` — async httpx test pattern, plus the `_register_and_login` helper worth copying
- `.claude/specs/accounts.md` — the spec this one is modelled on; same conventions apply
- `.claude/references/testing.md` — SAVEPOINT requirement, `auto_error=False`, real-Postgres-only
- `alembic/versions/7b6cb1ade18f_accounts.py` — migration style reference (Postgres enum create/drop pattern)

**Patterns to follow:**

- Routers thin: map HTTP ↔ service, translate service exceptions. See `app/routers/accounts.py`.
- Services take `db: AsyncSession` first; call `db.flush()` inside; `db.commit()` happens in the router.
- Typed exceptions per feature (`CategoryError`, `CategoryNotFound`, `CategoryForbidden`, `CategoryDuplicate`).
- Pydantic v2 response: `model_config = ConfigDict(from_attributes=True)`.
- Ownership check = filter on `Category.user_id == current_user.id` (or `IS NULL` for defaults in reads); missing custom row for another user → 404 (don't leak existence).
- UUID PKs via `mapped_column(primary_key=True, default=uuid.uuid4)`.
- Timestamps: `DateTime(timezone=True)` with `default=func.now()`.

**Key decisions already made:**

- `user_id` is **nullable**; defaults carry `user_id IS NULL` and `is_default = TRUE`. Custom categories carry a non-null `user_id` and `is_default = FALSE`.
- Custom-category name uniqueness is **per user, case-insensitive**. Enforced by a partial functional unique index: `UNIQUE (user_id, lower(name)) WHERE user_id IS NOT NULL`.
- Default-name uniqueness enforced by a second partial unique index: `UNIQUE (lower(name)) WHERE user_id IS NULL`.
- A user _is_ allowed to create a custom category with the same name as a default — the two indexes are disjoint and the PRD doesn't forbid it. Consistent with the per-user scope; re-visit if it causes UX confusion.
- **No soft delete.** Categories hard-delete. Feature 4 (Transactions) will later add the "409 if any transaction references this category" guard at the service layer when that FK exists — see "Out of scope" below.
- **Default categories are never copied per user.** Seeded exactly once, shared by all users. Returned by `GET /categories` via a single query with `WHERE user_id = :me OR user_id IS NULL`.
- **Seed strategy**: the Alembic migration inserts defaults via `op.bulk_insert`. `tests/conftest.py` seeds the same defaults after `Base.metadata.create_all` by calling a shared sync helper in `app/db/seed.py`. One source of truth for the default list.
- `PATCH` only updates `name`. `is_default` is immutable via the API.
- Default operations return **403** (`Cannot modify default category`) — not 404 — because the category is visible. For another user's custom category, return **404** (existence is private).
- Duplicate-name on create → **409** with `detail="Category name already exists"`.

## Constraints

**Must:**

- Every route uses `current_user: User = Depends(get_current_user)`.
- `GET /categories` returns `user_id = current_user.id` rows UNION `user_id IS NULL` rows in one query; order defaults first (by name), then customs (by `created_at`).
- Write operations target only rows where `user_id = current_user.id`.
- 403 for default, 404 for another user's custom — never mix them.
- Use `AsyncSession` throughout; no sync calls in the service/router.
- Response schema uses `ConfigDict(from_attributes=True)`.
- The same `DEFAULT_CATEGORIES` list in `app/db/seed.py` is the only place default names are defined — the migration imports it, and `tests/conftest.py` imports it.
- Alembic migration generated via `uv run alembic revision --autogenerate` and then hand-edited to add the `op.bulk_insert` + partial unique indexes (autogen won't produce those correctly).

**Must not:**

- No new runtime dependencies.
- Don't modify `auth.py`, `user.py`, `dependencies.py`, or the accounts feature beyond imports.
- Don't implement the "409 if transactions reference this category" check now — Transactions don't exist yet; attempting it would couple this feature to a non-existent model.
- Don't make a per-user copy of the defaults on registration. Defaults stay singletons.
- Don't add pagination to `GET /categories` — small set by definition.
- Don't allow toggling `is_default` via the API.

**Out of scope:**

- The **409-on-delete-when-transactions-exist** guard — deferred to Feature 4 (Transactions). That feature owns the FK and will add a service-layer check in `delete_category` at that time.
- Per-user override/rename of a default (e.g. "call Food → Groceries just for me") — PRD doesn't ask for it.
- Category icons / colors / ordering.
- Bulk import/export of categories.

## Tasks

### T1: Category model + migration + seed wiring

**Do:**

1. Create `app/db/seed.py`:

   ```python
   DEFAULT_CATEGORIES = [
       "Food", "Transport", "Housing", "Utilities",
       "Healthcare", "Entertainment", "Shopping", "Other",
   ]
   ```

   Also add a sync helper `def seed_default_categories(connection) -> None` that runs `INSERT ... ON CONFLICT DO NOTHING` against the `categories` table using the constant above. Shape it to be callable from Alembic (`op.get_bind()`) and from `conn.run_sync(seed_default_categories)` in tests.

2. Create `app/models/category.py`:
   - `class Category(Base)`, `__tablename__ = "categories"`:
     - `id: Mapped[uuid.UUID]` PK default `uuid.uuid4`
     - `user_id: Mapped[uuid.UUID | None]` FK→`users.id`, `nullable=True`, indexed
     - `name: Mapped[str]` `String`, `nullable=False`
     - `is_default: Mapped[bool]` `Boolean`, `nullable=False`, `default=False`, `server_default=sa.false()`
     - `created_at: Mapped[datetime]` `DateTime(timezone=True)`, `default=func.now()`, `nullable=False`
   - `__table_args__`:
     - `Index("ix_categories_user_id", "user_id")`
     - An `Index("ux_categories_user_lower_name", "user_id", func.lower(column("name")), unique=True, postgresql_where=text("user_id IS NOT NULL"))`
     - An `Index("ux_categories_default_lower_name", func.lower(column("name")), unique=True, postgresql_where=text("user_id IS NULL"))`

3. Register model: update `app/models/__init__.py` to import `Category` so Alembic autogen sees it.

4. Generate migration: `uv run alembic revision --autogenerate -m "categories"`. Inspect — autogen will produce the table and regular indexes but **will not** produce the partial unique indexes correctly. Hand-edit the migration to:
   - Drop any autogen-generated duplicate of the unique indexes that came out plain.
   - Emit the two partial unique indexes via `op.create_index(..., postgresql_where=sa.text("user_id IS NOT NULL"))` / `... IS NULL`.
   - At the end of `upgrade()`, import `DEFAULT_CATEGORIES` from `app.db.seed` and `op.bulk_insert` a row per name with `id=uuid4()`, `user_id=None`, `name=<name>`, `is_default=True`, `created_at=datetime.now(timezone.utc)`.
   - In `downgrade()`: drop the partial indexes before `drop_table`.

5. Update `tests/conftest.py`'s `create_tables` fixture: after `await conn.run_sync(Base.metadata.create_all)`, call `await conn.run_sync(seed_default_categories)`. Mirror the same call at teardown? No — `drop_all` wipes everything. Seed only on setup.

**Files:** `app/db/seed.py` (new), `app/models/category.py` (new), `app/models/__init__.py` (update), `alembic/versions/<hash>_categories.py` (new, then hand-edit), `tests/conftest.py` (update `create_tables`)

**Verify:**

- `uv run alembic upgrade head` — creates `categories` table + both partial unique indexes + inserts 8 default rows.
- `psql $DATABASE_URL -c '\d categories'` — shows columns, FK to users (nullable), both partial indexes.
- `psql $DATABASE_URL -c "select name, is_default, user_id from categories order by name;"` — 8 rows, all `user_id NULL`, all `is_default = t`.
- Uniqueness sanity: `psql -c "insert into categories (id, name, is_default, user_id) values (gen_random_uuid(), 'food', true, null);"` → fails with unique-constraint error (case-insensitive dupe of seeded `Food`).
- `uv run alembic downgrade -1` — drops cleanly.
- `uv run alembic upgrade head` — re-applies cleanly (idempotent insert).
- `uv run pytest tests/test_auth.py tests/test_accounts.py` — still green (conftest change didn't break anything).

### T2: Schemas + service layer

**Do:**

1. Create `app/schemas/category.py`:
   - `class CategoryCreate(BaseModel)`: `name: str` with `field_validator` rejecting empty/whitespace-only (mirror the `name_not_empty` pattern in `app/schemas/account.py`).
   - `class CategoryUpdate(BaseModel)`: `model_config = ConfigDict(extra="forbid")`; `name: Optional[str] = None` with the same non-empty validator (skip-on-None).
   - `class CategoryResponse(BaseModel)`: `model_config = ConfigDict(from_attributes=True)`; `id: UUID`, `name: str`, `is_default: bool`, `user_id: UUID | None`, `created_at: datetime`.

2. Create `app/services/category.py`:
   - Exceptions: `CategoryError(Exception)`, `CategoryNotFound(CategoryError)`, `CategoryForbidden(CategoryError)` (for operations on defaults), `CategoryDuplicate(CategoryError)`.
   - `async def list_categories(db, user_id) -> list[Category]` — `select().where(or_(user_id == :uid, user_id.is_(None))).order_by(is_default.desc(), name)`.
   - `async def get_category(db, user_id, category_id) -> Category` — returns the row if it's the user's custom OR a default. Raise `CategoryNotFound` otherwise. (Used by `update` / `delete` as the first lookup.)
   - `async def create_category(db, user_id, data: CategoryCreate) -> Category` — insert with `user_id=user_id`, `is_default=False`. Catch `IntegrityError` from the partial unique index and raise `CategoryDuplicate`. `db.flush()` — if the flush raises, rollback the savepoint / re-raise typed.
   - `async def update_category(db, user_id, category_id, data: CategoryUpdate) -> Category` — fetch via `get_category`; if `row.is_default` (or `row.user_id is None`) → raise `CategoryForbidden`; if `row.user_id != user_id` → raise `CategoryNotFound`; apply `model_dump(exclude_unset=True)`; flush (catch `IntegrityError` → `CategoryDuplicate`).
   - `async def delete_category(db, user_id, category_id) -> None` — fetch via `get_category`; same `is_default` → 403, `user_id != current` → 404 logic; `await db.delete(row)`; flush.

**Files:** `app/schemas/category.py` (new), `app/services/category.py` (new)

**Verify:**

- `uv run python -c "from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse; CategoryCreate(name='Coffee'); CategoryUpdate(name='X')"` — exits 0.
- `uv run python -c "from app.schemas.category import CategoryCreate; CategoryCreate(name='  ')"` — raises ValidationError (whitespace-only name).
- `uv run python -c "from app.schemas.category import CategoryUpdate; CategoryUpdate(extra='nope')"` — raises ValidationError (extra field forbidden).
- `uv run python -c "from app.services.category import CategoryNotFound, CategoryForbidden, CategoryDuplicate, create_category, list_categories, get_category, update_category, delete_category"` — exits 0.

### T3: Router + wire into app

**Do:**

1. Create `app/routers/categories.py`:
   - `router = APIRouter()`
   - `POST "/"` → 201, `response_model=CategoryResponse`. Body `CategoryCreate`. `create_category` → `await db.commit()` → return. Map `CategoryDuplicate` → 409 with `detail="Category name already exists"`.
   - `GET "/"` → `response_model=list[CategoryResponse]`. Return `await list_categories(db, current_user.id)`.
   - `PATCH "/{category_id}"` → `response_model=CategoryResponse`. Body `CategoryUpdate`. Map `CategoryForbidden` → 403 `detail="Cannot modify default category"`, `CategoryNotFound` → 404 `detail="Category not found"`, `CategoryDuplicate` → 409. Commit on success.
   - `DELETE "/{category_id}"` → 204. Same exception mapping as PATCH (minus duplicate). Commit on success.

   Every handler has `current_user: User = Depends(get_current_user)` and `db: AsyncSession = Depends(get_db)`.

2. Register in `app/main.py`: `from app.routers import categories` (keep imports alphabetized with existing) and `app.include_router(categories.router, prefix="/categories", tags=["categories"])`.

**Files:** `app/routers/categories.py` (new), `app/main.py` (update)

**Verify:** Manual curl sequence after `uv run uvicorn app.main:app`:

```
# register + login to get $ACCESS (reuse existing auth)
curl -s :8000/categories -H "authorization: bearer $ACCESS"
# → 200 list containing 8 defaults, all with is_default=true

curl -s -X POST :8000/categories -H "authorization: bearer $ACCESS" -H 'content-type: application/json' \
  -d '{"name":"Coffee"}'
# → 201 {name:"Coffee", is_default:false, user_id:"<uid>", ...}

curl -s -X POST :8000/categories -H "authorization: bearer $ACCESS" -H 'content-type: application/json' \
  -d '{"name":"coffee"}' -w '\n%{http_code}\n'
# → 409 (case-insensitive duplicate)

DEFAULT_ID=$(curl -s :8000/categories -H "authorization: bearer $ACCESS" | jq -r '.[] | select(.name=="Food") | .id')
curl -s -X PATCH :8000/categories/$DEFAULT_ID -H "authorization: bearer $ACCESS" -H 'content-type: application/json' \
  -d '{"name":"Groceries"}' -w '\n%{http_code}\n'
# → 403

curl -s -X DELETE :8000/categories/$DEFAULT_ID -H "authorization: bearer $ACCESS" -w '\n%{http_code}\n'
# → 403

curl -s :8000/categories -w '\n%{http_code}\n'
# → 401 {"detail":"Not authenticated"}
```

Also: visit `/docs` and confirm all 4 endpoints appear under the `categories` tag with the lock icon.

### T4: Tests

**Do:** Create `tests/test_categories.py`. Copy the `_register_and_login` helper from `tests/test_accounts.py` (or import it — inline copy is fine, matches existing pattern).

Test cases:

- `test_list_categories_returns_defaults_for_any_user` — fresh user → `GET /categories` → 8 defaults, all `is_default=True`, all `user_id=None`. Assert exact set of names matches `DEFAULT_CATEGORIES`.
- `test_list_categories_requires_auth` — no token → 401.
- `test_list_categories_includes_own_custom` — user creates "Coffee" → `GET` returns 9 entries (8 defaults + 1 custom).
- `test_list_categories_excludes_other_users_custom` — user A creates "ACoffee"; user B `GET` returns only defaults.
- `test_create_category_returns_201` — name stored, `is_default=False`, `user_id` set to caller.
- `test_create_category_rejects_empty_name` — `{"name":""}` → 422.
- `test_create_category_rejects_duplicate_case_insensitive` — create "Coffee", then "coffee" → 409.
- `test_create_category_same_name_as_default_allowed` — POST `{"name":"Food"}` → 201 (users _may_ shadow a default by name, per design decision in Context).
- `test_create_category_same_name_different_users_allowed` — user A creates "Coffee", user B creates "Coffee" → both 201.
- `test_patch_category_default_returns_403` — pick a default id from `GET /categories`; PATCH name → 403.
- `test_patch_category_other_users_returns_404` — user A creates; user B PATCHes A's id → 404.
- `test_patch_category_updates_name` — user creates "Coffee", PATCHes to "Espresso" → 200, name updated.
- `test_patch_category_rejects_extra_fields` — `{"is_default": true}` or `{"unknown":"x"}` → 422.
- `test_patch_category_duplicate_returns_409` — user creates "Coffee" and "Tea"; PATCH "Tea" → "coffee" → 409.
- `test_delete_category_default_returns_403` — pick a default id; DELETE → 403.
- `test_delete_category_other_users_returns_404` — user A creates; user B DELETEs → 404.
- `test_delete_category_success_is_hard_delete` — user creates, DELETEs, then queries DB via the `db` fixture to assert the row is gone (`scalar_one_or_none()` is `None`).

**Files:** `tests/test_categories.py` (new)

**Verify:** `uv run pytest -x -v tests/test_categories.py` — all green. `uv run pytest` — full suite green (no auth / accounts regressions).

## Done

- [ ] `uv run alembic upgrade head` on an empty DB creates `categories` table, both partial unique indexes, and inserts the 8 default rows.
- [ ] `uv run pytest` — new categories tests plus all pre-existing auth / accounts tests pass.
- [ ] `uv run uvicorn app.main:app` boots; `/docs` shows 4 categories endpoints under the `categories` tag, each with the auth lock.
- [ ] Manual curl sequence in T3 succeeds end-to-end: defaults visible, custom create works, case-insensitive dupe → 409, default mutate → 403.
- [ ] No regressions: auth + accounts suites still green.
- [ ] `DEFAULT_CATEGORIES` is defined once in `app/db/seed.py` and referenced by both the migration and `tests/conftest.py`.

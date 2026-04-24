from httpx import AsyncClient
from sqlalchemy import select

from app.db.seed import DEFAULT_CATEGORIES
from app.models.category import Category


async def _register_and_login(client: AsyncClient, email: str) -> dict:
    await client.post("/auth/register", json={"email": email, "password": "password123"})
    resp = await client.post("/auth/login", json={"email": email, "password": "password123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_list_categories_returns_defaults_for_any_user(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_list1@example.com")
    resp = await async_client.get("/categories/", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 8
    assert all(c["is_default"] is True for c in body)
    assert all(c["user_id"] is None for c in body)
    assert {c["name"] for c in body} == set(DEFAULT_CATEGORIES)


async def test_list_categories_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/categories/")
    assert resp.status_code == 401


async def test_list_categories_includes_own_custom(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_list2@example.com")
    await async_client.post("/categories/", json={"name": "Coffee"}, headers=headers)
    resp = await async_client.get("/categories/", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 9


async def test_list_categories_excludes_other_users_custom(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "cat_lista@example.com")
    headers_b = await _register_and_login(async_client, "cat_listb@example.com")
    await async_client.post("/categories/", json={"name": "ACoffee"}, headers=headers_a)
    resp = await async_client.get("/categories/", headers=headers_b)
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert "ACoffee" not in names
    assert len(resp.json()) == 8


async def test_create_category_returns_201(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_create1@example.com")
    resp = await async_client.post("/categories/", json={"name": "Subscriptions"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Subscriptions"
    assert body["is_default"] is False
    assert body["user_id"] is not None


async def test_create_category_rejects_empty_name(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_create2@example.com")
    resp = await async_client.post("/categories/", json={"name": ""}, headers=headers)
    assert resp.status_code == 422


async def test_create_category_rejects_duplicate_case_insensitive(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_create3@example.com")
    await async_client.post("/categories/", json={"name": "Coffee"}, headers=headers)
    resp = await async_client.post("/categories/", json={"name": "coffee"}, headers=headers)
    assert resp.status_code == 409


async def test_create_category_same_name_as_default_allowed(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_create4@example.com")
    resp = await async_client.post("/categories/", json={"name": "Food"}, headers=headers)
    assert resp.status_code == 201


async def test_create_category_same_name_different_users_allowed(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "cat_createa@example.com")
    headers_b = await _register_and_login(async_client, "cat_createb@example.com")
    resp_a = await async_client.post("/categories/", json={"name": "Coffee"}, headers=headers_a)
    resp_b = await async_client.post("/categories/", json={"name": "Coffee"}, headers=headers_b)
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201


async def test_patch_category_default_returns_403(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_patch1@example.com")
    categories = (await async_client.get("/categories/", headers=headers)).json()
    default_id = next(c["id"] for c in categories if c["is_default"])
    resp = await async_client.patch(f"/categories/{default_id}", json={"name": "Groceries"}, headers=headers)
    assert resp.status_code == 403


async def test_patch_category_other_users_returns_404(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "cat_patcha@example.com")
    headers_b = await _register_and_login(async_client, "cat_patchb@example.com")
    resp = await async_client.post("/categories/", json={"name": "ACustom"}, headers=headers_a)
    cat_id = resp.json()["id"]
    resp = await async_client.patch(f"/categories/{cat_id}", json={"name": "Hacked"}, headers=headers_b)
    assert resp.status_code == 404


async def test_patch_category_updates_name(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_patch2@example.com")
    resp = await async_client.post("/categories/", json={"name": "Coffee"}, headers=headers)
    cat_id = resp.json()["id"]
    resp = await async_client.patch(f"/categories/{cat_id}", json={"name": "Espresso"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Espresso"


async def test_patch_category_rejects_extra_fields(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_patch3@example.com")
    resp = await async_client.post("/categories/", json={"name": "Coffee"}, headers=headers)
    cat_id = resp.json()["id"]
    resp = await async_client.patch(f"/categories/{cat_id}", json={"is_default": True}, headers=headers)
    assert resp.status_code == 422
    resp2 = await async_client.patch(f"/categories/{cat_id}", json={"unknown": "x"}, headers=headers)
    assert resp2.status_code == 422


async def test_patch_category_duplicate_returns_409(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_patch4@example.com")
    await async_client.post("/categories/", json={"name": "Coffee"}, headers=headers)
    resp = await async_client.post("/categories/", json={"name": "Tea"}, headers=headers)
    tea_id = resp.json()["id"]
    resp = await async_client.patch(f"/categories/{tea_id}", json={"name": "coffee"}, headers=headers)
    assert resp.status_code == 409


async def test_delete_category_default_returns_403(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "cat_del1@example.com")
    categories = (await async_client.get("/categories/", headers=headers)).json()
    default_id = next(c["id"] for c in categories if c["is_default"])
    resp = await async_client.delete(f"/categories/{default_id}", headers=headers)
    assert resp.status_code == 403


async def test_delete_category_other_users_returns_404(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "cat_dela@example.com")
    headers_b = await _register_and_login(async_client, "cat_delb@example.com")
    resp = await async_client.post("/categories/", json={"name": "ACustom2"}, headers=headers_a)
    cat_id = resp.json()["id"]
    resp = await async_client.delete(f"/categories/{cat_id}", headers=headers_b)
    assert resp.status_code == 404


async def test_delete_category_success_is_hard_delete(async_client: AsyncClient, db):
    headers = await _register_and_login(async_client, "cat_del2@example.com")
    resp = await async_client.post("/categories/", json={"name": "ToDelete"}, headers=headers)
    cat_id = resp.json()["id"]
    del_resp = await async_client.delete(f"/categories/{cat_id}", headers=headers)
    assert del_resp.status_code == 204
    result = await db.execute(select(Category).where(Category.id == cat_id))
    assert result.scalar_one_or_none() is None

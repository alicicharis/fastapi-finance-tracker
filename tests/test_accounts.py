from httpx import AsyncClient
from sqlalchemy import select

from app.models.account import Account


async def _register_and_login(client: AsyncClient, email: str) -> dict:
    await client.post("/auth/register", json={"email": email, "password": "password123"})
    resp = await client.post("/auth/login", json={"email": email, "password": "password123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_account_returns_201_with_defaults(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "create1@example.com")
    resp = await async_client.post("/accounts/", json={"name": "Chase", "account_type": "checking"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["currency"] == "USD"
    assert body["name"] == "Chase"
    assert body["account_type"] == "checking"


async def test_create_account_requires_auth(async_client: AsyncClient):
    resp = await async_client.post("/accounts/", json={"name": "Chase", "account_type": "checking"})
    assert resp.status_code == 401


async def test_create_account_rejects_invalid_type(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "create2@example.com")
    resp = await async_client.post("/accounts/", json={"name": "Chase", "account_type": "invalid"}, headers=headers)
    assert resp.status_code == 422


async def test_create_account_rejects_invalid_currency(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "create3@example.com")
    resp = await async_client.post("/accounts/", json={"name": "Chase", "account_type": "checking", "currency": "us"}, headers=headers)
    assert resp.status_code == 422
    resp2 = await async_client.post("/accounts/", json={"name": "Chase", "account_type": "checking", "currency": "USDX"}, headers=headers)
    assert resp2.status_code == 422


async def test_list_accounts_returns_only_current_users(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "lista@example.com")
    headers_b = await _register_and_login(async_client, "listb@example.com")

    await async_client.post("/accounts/", json={"name": "A1", "account_type": "checking"}, headers=headers_a)
    await async_client.post("/accounts/", json={"name": "A2", "account_type": "savings"}, headers=headers_a)
    await async_client.post("/accounts/", json={"name": "B1", "account_type": "cash"}, headers=headers_b)

    resp_a = await async_client.get("/accounts/", headers=headers_a)
    resp_b = await async_client.get("/accounts/", headers=headers_b)

    assert resp_a.status_code == 200
    assert len(resp_a.json()) == 2
    assert resp_b.status_code == 200
    assert len(resp_b.json()) == 1


async def test_list_accounts_excludes_soft_deleted(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "listdel@example.com")
    resp = await async_client.post("/accounts/", json={"name": "ToDelete", "account_type": "cash"}, headers=headers)
    account_id = resp.json()["id"]

    await async_client.delete(f"/accounts/{account_id}", headers=headers)

    resp = await async_client.get("/accounts/", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_account_404_for_other_users_account(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "geta@example.com")
    headers_b = await _register_and_login(async_client, "getb@example.com")

    resp = await async_client.post("/accounts/", json={"name": "A account", "account_type": "checking"}, headers=headers_a)
    account_id = resp.json()["id"]

    resp = await async_client.get(f"/accounts/{account_id}", headers=headers_b)
    assert resp.status_code == 404


async def test_patch_account_partial_update(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "patch1@example.com")
    resp = await async_client.post("/accounts/", json={"name": "Original", "account_type": "checking", "currency": "EUR"}, headers=headers)
    account_id = resp.json()["id"]

    resp = await async_client.patch(f"/accounts/{account_id}", json={"name": "Updated"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Updated"
    assert body["account_type"] == "checking"
    assert body["currency"] == "EUR"


async def test_patch_account_404_for_other_users_account(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "patcha@example.com")
    headers_b = await _register_and_login(async_client, "patchb@example.com")

    resp = await async_client.post("/accounts/", json={"name": "A account", "account_type": "checking"}, headers=headers_a)
    account_id = resp.json()["id"]

    resp = await async_client.patch(f"/accounts/{account_id}", json={"name": "Hacked"}, headers=headers_b)
    assert resp.status_code == 404


async def test_patch_account_rejects_extra_fields(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "patch2@example.com")
    resp = await async_client.post("/accounts/", json={"name": "Acct", "account_type": "cash"}, headers=headers)
    account_id = resp.json()["id"]

    resp = await async_client.patch(f"/accounts/{account_id}", json={"name": "New", "unknown_field": "x"}, headers=headers)
    assert resp.status_code == 422


async def test_delete_account_returns_204_and_is_soft(async_client: AsyncClient, db):
    headers = await _register_and_login(async_client, "softdel@example.com")
    resp = await async_client.post("/accounts/", json={"name": "SoftDel", "account_type": "savings"}, headers=headers)
    account_id = resp.json()["id"]

    del_resp = await async_client.delete(f"/accounts/{account_id}", headers=headers)
    assert del_resp.status_code == 204

    result = await db.execute(select(Account).where(Account.id == account_id))
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.deleted_at is not None


async def test_delete_account_is_idempotent_second_call_404(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "delidempotent@example.com")
    resp = await async_client.post("/accounts/", json={"name": "Acct", "account_type": "other"}, headers=headers)
    account_id = resp.json()["id"]

    await async_client.delete(f"/accounts/{account_id}", headers=headers)
    resp2 = await async_client.delete(f"/accounts/{account_id}", headers=headers)
    assert resp2.status_code == 404


async def test_delete_account_404_for_other_users_account(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "dela@example.com")
    headers_b = await _register_and_login(async_client, "delb@example.com")

    resp = await async_client.post("/accounts/", json={"name": "A account", "account_type": "credit"}, headers=headers_a)
    account_id = resp.json()["id"]

    resp = await async_client.delete(f"/accounts/{account_id}", headers=headers_b)
    assert resp.status_code == 404

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> dict:
    await client.post("/auth/register", json={"email": email, "password": "password123"})
    resp = await client.post("/auth/login", json={"email": email, "password": "password123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_account(client: AsyncClient, headers: dict, name: str = "Checking") -> str:
    resp = await client.post("/accounts/", json={"name": name, "account_type": "checking"}, headers=headers)
    return resp.json()["id"]


async def _create_category(client: AsyncClient, headers: dict, name: str = "Food") -> str:
    resp = await client.post("/categories/", json={"name": name}, headers=headers)
    return resp.json()["id"]


def _tx_payload(account_id: str, category_id: str, **overrides) -> dict:
    base = {
        "account_id": account_id,
        "category_id": category_id,
        "amount": "50.00",
        "type": "expense",
        "date": "2026-01-15",
    }
    base.update(overrides)
    return base


async def test_create_returns_201_with_correct_fields(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txcreate1@example.com")
    account_id = await _create_account(async_client, headers)
    category_id = await _create_category(async_client, headers)

    resp = await async_client.post("/transactions/", json=_tx_payload(account_id, category_id, description="Lunch"), headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["amount"] == "50.00"
    assert body["type"] == "expense"
    assert body["date"] == "2026-01-15"
    assert body["description"] == "Lunch"
    assert "id" in body
    assert "user_id" in body
    assert "created_at" in body


async def test_create_rejects_zero_amount(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txamount1@example.com")
    account_id = await _create_account(async_client, headers)
    category_id = await _create_category(async_client, headers)

    resp = await async_client.post("/transactions/", json=_tx_payload(account_id, category_id, amount="0"), headers=headers)
    assert resp.status_code == 422


async def test_create_rejects_negative_amount(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txamount2@example.com")
    account_id = await _create_account(async_client, headers)
    category_id = await _create_category(async_client, headers)

    resp = await async_client.post("/transactions/", json=_tx_payload(account_id, category_id, amount="-5"), headers=headers)
    assert resp.status_code == 422


async def test_create_with_other_users_account_returns_404(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "txacct_a@example.com")
    headers_b = await _register_and_login(async_client, "txacct_b@example.com")

    account_id_a = await _create_account(async_client, headers_a)
    category_id_b = await _create_category(async_client, headers_b)

    resp = await async_client.post("/transactions/", json=_tx_payload(account_id_a, category_id_b), headers=headers_b)
    assert resp.status_code == 404


async def test_create_with_other_users_category_returns_404(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "txcat_a@example.com")
    headers_b = await _register_and_login(async_client, "txcat_b@example.com")

    account_id_b = await _create_account(async_client, headers_b)
    category_id_a = await _create_category(async_client, headers_a)

    resp = await async_client.post("/transactions/", json=_tx_payload(account_id_b, category_id_a), headers=headers_b)
    assert resp.status_code == 404


async def test_list_returns_only_current_users_transactions(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "txlist_a@example.com")
    headers_b = await _register_and_login(async_client, "txlist_b@example.com")

    acct_a = await _create_account(async_client, headers_a)
    cat_a = await _create_category(async_client, headers_a)
    acct_b = await _create_account(async_client, headers_b)
    cat_b = await _create_category(async_client, headers_b)

    await async_client.post("/transactions/", json=_tx_payload(acct_a, cat_a), headers=headers_a)
    await async_client.post("/transactions/", json=_tx_payload(acct_a, cat_a), headers=headers_a)
    await async_client.post("/transactions/", json=_tx_payload(acct_b, cat_b), headers=headers_b)

    resp_a = await async_client.get("/transactions/", headers=headers_a)
    resp_b = await async_client.get("/transactions/", headers=headers_b)

    assert len(resp_a.json()) == 2
    assert len(resp_b.json()) == 1


async def test_list_filters_by_account_id(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txfilt_acct@example.com")
    acct1 = await _create_account(async_client, headers, "Acct1")
    acct2 = await _create_account(async_client, headers, "Acct2")
    cat = await _create_category(async_client, headers)

    await async_client.post("/transactions/", json=_tx_payload(acct1, cat), headers=headers)
    await async_client.post("/transactions/", json=_tx_payload(acct2, cat), headers=headers)

    resp = await async_client.get(f"/transactions/?account_id={acct1}", headers=headers)
    assert len(resp.json()) == 1
    assert resp.json()[0]["account_id"] == acct1


async def test_list_filters_by_category_id(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txfilt_cat@example.com")
    acct = await _create_account(async_client, headers)
    cat1 = await _create_category(async_client, headers, "Cat1")
    cat2 = await _create_category(async_client, headers, "Cat2")

    await async_client.post("/transactions/", json=_tx_payload(acct, cat1), headers=headers)
    await async_client.post("/transactions/", json=_tx_payload(acct, cat2), headers=headers)

    resp = await async_client.get(f"/transactions/?category_id={cat2}", headers=headers)
    assert len(resp.json()) == 1
    assert resp.json()[0]["category_id"] == cat2


async def test_list_filters_by_date_range(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txfilt_date@example.com")
    acct = await _create_account(async_client, headers)
    cat = await _create_category(async_client, headers)

    await async_client.post("/transactions/", json=_tx_payload(acct, cat, date="2026-01-10"), headers=headers)
    await async_client.post("/transactions/", json=_tx_payload(acct, cat, date="2026-02-10"), headers=headers)
    await async_client.post("/transactions/", json=_tx_payload(acct, cat, date="2026-03-10"), headers=headers)

    resp = await async_client.get("/transactions/?start_date=2026-02-01&end_date=2026-02-28", headers=headers)
    assert len(resp.json()) == 1
    assert resp.json()[0]["date"] == "2026-02-10"


async def test_list_filters_by_type(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txfilt_type@example.com")
    acct = await _create_account(async_client, headers)
    cat = await _create_category(async_client, headers)

    await async_client.post("/transactions/", json=_tx_payload(acct, cat, type="income"), headers=headers)
    await async_client.post("/transactions/", json=_tx_payload(acct, cat, type="expense"), headers=headers)

    resp = await async_client.get("/transactions/?type=income", headers=headers)
    assert len(resp.json()) == 1
    assert resp.json()[0]["type"] == "income"


async def test_list_respects_limit_and_offset(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txpaginate@example.com")
    acct = await _create_account(async_client, headers)
    cat = await _create_category(async_client, headers)

    for i in range(5):
        await async_client.post("/transactions/", json=_tx_payload(acct, cat, date=f"2026-01-{i+1:02d}"), headers=headers)

    resp_limit = await async_client.get("/transactions/?limit=2", headers=headers)
    assert len(resp_limit.json()) == 2

    resp_offset = await async_client.get("/transactions/?limit=10&offset=3", headers=headers)
    assert len(resp_offset.json()) == 2


async def test_get_single_happy_path(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txget1@example.com")
    acct = await _create_account(async_client, headers)
    cat = await _create_category(async_client, headers)

    create_resp = await async_client.post("/transactions/", json=_tx_payload(acct, cat), headers=headers)
    tx_id = create_resp.json()["id"]

    resp = await async_client.get(f"/transactions/{tx_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == tx_id


async def test_get_single_404_for_other_users_transaction(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "txget_a@example.com")
    headers_b = await _register_and_login(async_client, "txget_b@example.com")

    acct_a = await _create_account(async_client, headers_a)
    cat_a = await _create_category(async_client, headers_a)

    create_resp = await async_client.post("/transactions/", json=_tx_payload(acct_a, cat_a), headers=headers_a)
    tx_id = create_resp.json()["id"]

    resp = await async_client.get(f"/transactions/{tx_id}", headers=headers_b)
    assert resp.status_code == 404


async def test_patch_partial_update_untouched_fields_unchanged(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txpatch1@example.com")
    acct = await _create_account(async_client, headers)
    cat = await _create_category(async_client, headers)

    create_resp = await async_client.post(
        "/transactions/", json=_tx_payload(acct, cat, description="Original", amount="75.00"), headers=headers
    )
    tx_id = create_resp.json()["id"]

    resp = await async_client.patch(f"/transactions/{tx_id}", json={"description": "Updated"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Updated"
    assert body["amount"] == "75.00"
    assert body["type"] == "expense"


async def test_patch_with_other_users_account_returns_404(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "txpatch_a@example.com")
    headers_b = await _register_and_login(async_client, "txpatch_b@example.com")

    acct_a = await _create_account(async_client, headers_a)
    acct_b = await _create_account(async_client, headers_b)
    cat_a = await _create_category(async_client, headers_a)

    create_resp = await async_client.post("/transactions/", json=_tx_payload(acct_a, cat_a), headers=headers_a)
    tx_id = create_resp.json()["id"]

    resp = await async_client.patch(f"/transactions/{tx_id}", json={"account_id": acct_b}, headers=headers_a)
    assert resp.status_code == 404


async def test_delete_returns_204_and_subsequent_get_returns_404(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "txdelete1@example.com")
    acct = await _create_account(async_client, headers)
    cat = await _create_category(async_client, headers)

    create_resp = await async_client.post("/transactions/", json=_tx_payload(acct, cat), headers=headers)
    tx_id = create_resp.json()["id"]

    del_resp = await async_client.delete(f"/transactions/{tx_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await async_client.get(f"/transactions/{tx_id}", headers=headers)
    assert get_resp.status_code == 404


async def test_create_requires_auth(async_client: AsyncClient):
    resp = await async_client.post("/transactions/", json={"account_id": "x", "category_id": "x", "amount": "10", "type": "expense", "date": "2026-01-01"})
    assert resp.status_code == 401


async def test_list_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/transactions/")
    assert resp.status_code == 401


async def test_get_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/transactions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


async def test_patch_requires_auth(async_client: AsyncClient):
    resp = await async_client.patch("/transactions/00000000-0000-0000-0000-000000000000", json={"description": "x"})
    assert resp.status_code == 401


async def test_delete_requires_auth(async_client: AsyncClient):
    resp = await async_client.delete("/transactions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401

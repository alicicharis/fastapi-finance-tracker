from datetime import date

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> dict:
    await client.post("/auth/register", json={"email": email, "password": "password123"})
    resp = await client.post("/auth/login", json={"email": email, "password": "password123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_category(client: AsyncClient, headers: dict, name: str = "Food") -> str:
    resp = await client.post("/categories/", json={"name": name}, headers=headers)
    return resp.json()["id"]


async def _create_account(client: AsyncClient, headers: dict) -> str:
    resp = await client.post("/accounts/", json={"name": "Checking", "account_type": "checking"}, headers=headers)
    return resp.json()["id"]


def _budget_payload(category_id: str, **overrides) -> dict:
    base = {
        "category_id": category_id,
        "month": "2026-04-01",
        "amount_limit": "500.00",
    }
    base.update(overrides)
    return base


async def test_create_returns_201_with_computed_fields(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetcreate1@example.com")
    cat = await _create_category(async_client, headers)

    resp = await async_client.post("/budgets/", json=_budget_payload(cat), headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert float(body["amount_spent"]) == 0.0
    assert body["percent_used"] == 0.0
    assert "id" in body
    assert "user_id" in body
    assert "created_at" in body


async def test_create_rejects_zero_amount_limit(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetlimit1@example.com")
    cat = await _create_category(async_client, headers)

    resp = await async_client.post("/budgets/", json=_budget_payload(cat, amount_limit="0"), headers=headers)
    assert resp.status_code == 422


async def test_create_rejects_negative_amount_limit(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetlimit2@example.com")
    cat = await _create_category(async_client, headers)

    resp = await async_client.post("/budgets/", json=_budget_payload(cat, amount_limit="-10"), headers=headers)
    assert resp.status_code == 422


async def test_create_duplicate_returns_409(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetdup1@example.com")
    cat = await _create_category(async_client, headers)

    await async_client.post("/budgets/", json=_budget_payload(cat), headers=headers)
    resp = await async_client.post("/budgets/", json=_budget_payload(cat), headers=headers)
    assert resp.status_code == 409


async def test_create_with_other_users_category_returns_404(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "budgetcat_a@example.com")
    headers_b = await _register_and_login(async_client, "budgetcat_b@example.com")

    cat_a = await _create_category(async_client, headers_a)

    resp = await async_client.post("/budgets/", json=_budget_payload(cat_a), headers=headers_b)
    assert resp.status_code == 404


async def test_list_returns_only_current_users_budgets_for_month(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "budgetlist_a@example.com")
    headers_b = await _register_and_login(async_client, "budgetlist_b@example.com")

    cat_a = await _create_category(async_client, headers_a)
    cat_b = await _create_category(async_client, headers_b)

    await async_client.post("/budgets/", json=_budget_payload(cat_a), headers=headers_a)
    await async_client.post("/budgets/", json=_budget_payload(cat_b), headers=headers_b)

    resp_a = await async_client.get("/budgets/?month=2026-04", headers=headers_a)
    resp_b = await async_client.get("/budgets/?month=2026-04", headers=headers_b)

    assert len(resp_a.json()) == 1
    assert len(resp_b.json()) == 1
    assert resp_a.json()[0]["category_id"] == cat_a


async def test_list_defaults_to_current_month(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetdefault@example.com")
    cat = await _create_category(async_client, headers)

    today = date.today()
    current_month_first = today.replace(day=1).isoformat()

    await async_client.post("/budgets/", json=_budget_payload(cat, month=current_month_first), headers=headers)

    resp = await async_client.get("/budgets/", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_amount_spent_reflects_expense_transactions(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetspent1@example.com")
    cat = await _create_category(async_client, headers)
    acct = await _create_account(async_client, headers)

    await async_client.post("/budgets/", json=_budget_payload(cat, month="2026-04-01", amount_limit="500.00"), headers=headers)

    await async_client.post("/transactions/", json={
        "account_id": acct, "category_id": cat, "amount": "100.00", "type": "expense", "date": "2026-04-10"
    }, headers=headers)
    await async_client.post("/transactions/", json={
        "account_id": acct, "category_id": cat, "amount": "50.00", "type": "expense", "date": "2026-04-15"
    }, headers=headers)

    resp = await async_client.get("/budgets/?month=2026-04", headers=headers)
    assert resp.status_code == 200
    budget = resp.json()[0]
    assert budget["amount_spent"] == "150.00"


async def test_amount_spent_excludes_income_transactions(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetincome1@example.com")
    cat = await _create_category(async_client, headers)
    acct = await _create_account(async_client, headers)

    await async_client.post("/budgets/", json=_budget_payload(cat, month="2026-04-01", amount_limit="500.00"), headers=headers)

    await async_client.post("/transactions/", json={
        "account_id": acct, "category_id": cat, "amount": "200.00", "type": "income", "date": "2026-04-10"
    }, headers=headers)

    resp = await async_client.get("/budgets/?month=2026-04", headers=headers)
    budget = resp.json()[0]
    assert float(budget["amount_spent"]) == 0.0


async def test_percent_used_computed_correctly(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetpct1@example.com")
    cat = await _create_category(async_client, headers)
    acct = await _create_account(async_client, headers)

    await async_client.post("/budgets/", json=_budget_payload(cat, month="2026-04-01", amount_limit="500.00"), headers=headers)
    await async_client.post("/transactions/", json={
        "account_id": acct, "category_id": cat, "amount": "400.00", "type": "expense", "date": "2026-04-10"
    }, headers=headers)

    resp = await async_client.get("/budgets/?month=2026-04", headers=headers)
    budget = resp.json()[0]
    assert budget["percent_used"] == 80.0


async def test_get_single_happy_path(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetget1@example.com")
    cat = await _create_category(async_client, headers)

    create_resp = await async_client.post("/budgets/", json=_budget_payload(cat), headers=headers)
    budget_id = create_resp.json()["id"]

    resp = await async_client.get(f"/budgets/{budget_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == budget_id


async def test_get_single_404_for_other_users_budget(async_client: AsyncClient):
    headers_a = await _register_and_login(async_client, "budgetget_a@example.com")
    headers_b = await _register_and_login(async_client, "budgetget_b@example.com")

    cat_a = await _create_category(async_client, headers_a)
    create_resp = await async_client.post("/budgets/", json=_budget_payload(cat_a), headers=headers_a)
    budget_id = create_resp.json()["id"]

    resp = await async_client.get(f"/budgets/{budget_id}", headers=headers_b)
    assert resp.status_code == 404


async def test_patch_amount_limit(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetpatch1@example.com")
    cat = await _create_category(async_client, headers)

    create_resp = await async_client.post("/budgets/", json=_budget_payload(cat, amount_limit="500.00"), headers=headers)
    budget_id = create_resp.json()["id"]
    original_cat = create_resp.json()["category_id"]
    original_month = create_resp.json()["month"]

    resp = await async_client.patch(f"/budgets/{budget_id}", json={"amount_limit": "750.00"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["amount_limit"] == "750.00"
    assert body["category_id"] == original_cat
    assert body["month"] == original_month


async def test_delete_returns_204_and_subsequent_get_returns_404(async_client: AsyncClient):
    headers = await _register_and_login(async_client, "budgetdelete1@example.com")
    cat = await _create_category(async_client, headers)

    create_resp = await async_client.post("/budgets/", json=_budget_payload(cat), headers=headers)
    budget_id = create_resp.json()["id"]

    del_resp = await async_client.delete(f"/budgets/{budget_id}", headers=headers)
    assert del_resp.status_code == 204

    get_resp = await async_client.get(f"/budgets/{budget_id}", headers=headers)
    assert get_resp.status_code == 404


async def test_create_requires_auth(async_client: AsyncClient):
    resp = await async_client.post("/budgets/", json={"category_id": "00000000-0000-0000-0000-000000000000", "month": "2026-04-01", "amount_limit": "100"})
    assert resp.status_code == 401


async def test_list_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/budgets/")
    assert resp.status_code == 401


async def test_get_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/budgets/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


async def test_patch_requires_auth(async_client: AsyncClient):
    resp = await async_client.patch("/budgets/00000000-0000-0000-0000-000000000000", json={"amount_limit": "100"})
    assert resp.status_code == 401


async def test_delete_requires_auth(async_client: AsyncClient):
    resp = await async_client.delete("/budgets/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401

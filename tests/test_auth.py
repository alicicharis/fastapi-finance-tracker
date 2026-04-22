from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt

from app.config import settings


async def test_register_returns_201_and_user(async_client: AsyncClient):
    resp = await async_client.post("/auth/register", json={"email": "user@example.com", "password": "password123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "user@example.com"
    assert "id" in body
    assert "hashed_password" not in body


async def test_register_duplicate_email_returns_409(async_client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "password123"}
    await async_client.post("/auth/register", json=payload)
    resp = await async_client.post("/auth/register", json=payload)
    assert resp.status_code == 409


async def test_register_weak_password_returns_422(async_client: AsyncClient):
    resp = await async_client.post("/auth/register", json={"email": "weak@example.com", "password": "short"})
    assert resp.status_code == 422


async def test_login_success_returns_tokens(async_client: AsyncClient):
    await async_client.post("/auth/register", json={"email": "login@example.com", "password": "password123"})
    resp = await async_client.post("/auth/login", json={"email": "login@example.com", "password": "password123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_returns_401(async_client: AsyncClient):
    await async_client.post("/auth/register", json={"email": "wrongpw@example.com", "password": "password123"})
    resp = await async_client.post("/auth/login", json={"email": "wrongpw@example.com", "password": "wrongpassword"})
    assert resp.status_code == 401


async def test_login_unknown_email_returns_401(async_client: AsyncClient):
    resp = await async_client.post("/auth/login", json={"email": "nobody@example.com", "password": "password123"})
    assert resp.status_code == 401


async def test_protected_route_requires_token(async_client: AsyncClient):
    resp = await async_client.get("/auth/me")
    assert resp.status_code == 401


async def test_protected_route_accepts_valid_token(async_client: AsyncClient):
    await async_client.post("/auth/register", json={"email": "me@example.com", "password": "password123"})
    login = await async_client.post("/auth/login", json={"email": "me@example.com", "password": "password123"})
    token = login.json()["access_token"]

    resp = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


async def test_protected_route_rejects_expired_token(async_client: AsyncClient):
    await async_client.post("/auth/register", json={"email": "expired@example.com", "password": "password123"})
    login = await async_client.post("/auth/login", json={"email": "expired@example.com", "password": "password123"})
    body = login.json()

    user_id = (await async_client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})).json()["id"]

    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_token = jwt.encode(
        {"sub": user_id, "iat": past, "exp": past + timedelta(minutes=1)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    resp = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


async def test_refresh_rotates_and_old_token_is_rejected(async_client: AsyncClient):
    await async_client.post("/auth/register", json={"email": "refresh@example.com", "password": "password123"})
    login = await async_client.post("/auth/login", json={"email": "refresh@example.com", "password": "password123"})
    original_refresh = login.json()["refresh_token"]

    resp = await async_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert "access_token" in new_tokens
    assert new_tokens["refresh_token"] != original_refresh

    resp2 = await async_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert resp2.status_code == 401


async def test_refresh_with_invalid_token_returns_401(async_client: AsyncClient):
    resp = await async_client.post("/auth/refresh", json={"refresh_token": "totally-invalid-token"})
    assert resp.status_code == 401

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_me(client: AsyncClient):
    email = f"auth-{uuid.uuid4()}@example.com"
    password = "password"

    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    assert r.json()["email"] == email

    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email

import os
import sys
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app
from app.db.session import AsyncSessionLocal


@pytest.fixture(autouse=True)
async def _clean_db():
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE analytics_events, subscriptions, feedback, ai_usage, sprint_reflections, sprint_events, sprints, microsteps, tasks, users RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_headers(client: AsyncClient):
    email = f"user-{uuid.uuid4()}@example.com"
    password = "password"

    resp = await client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}

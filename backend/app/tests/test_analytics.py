import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_analytics_events_inserted_on_register_and_task_create(
    client: AsyncClient,
):
    email = f"analytics-{uuid.uuid4()}@example.com"
    password = "password"

    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201

    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/tasks", json={"title": "Test task"}, headers=headers)
    assert r.status_code == 201

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text("SELECT event_name FROM analytics_events ORDER BY created_at ASC")
            )
        ).fetchall()
        event_names = [r[0] for r in rows]

    assert "user_registered" in event_names
    assert "user_logged_in" in event_names
    assert "task_created" in event_names

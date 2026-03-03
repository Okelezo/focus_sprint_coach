import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_happy_path_task_sprint_flow(client: AsyncClient, auth_headers: dict[str, str]):
    r = await client.post("/tasks", json={"title": "Write spec"}, headers=auth_headers)
    assert r.status_code == 201
    task_id = r.json()["id"]

    r = await client.post(
        f"/tasks/{task_id}/microsteps",
        json={"text": "Open editor", "order_index": 1},
        headers=auth_headers,
    )
    assert r.status_code == 201

    r = await client.post(
        "/sprints/start",
        json={"task_id": task_id, "duration_minutes": 25},
        headers=auth_headers,
    )
    assert r.status_code == 201
    sprint_id = r.json()["id"]

    r = await client.post(
        f"/sprints/{sprint_id}/events",
        json={"type": "note", "payload": {"text": "Feeling good"}},
        headers=auth_headers,
    )
    assert r.status_code == 201

    r = await client.post(
        f"/sprints/{sprint_id}/finish",
        json={"status": "completed"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"

    r = await client.post(
        f"/sprints/{sprint_id}/reflection",
        json={"outcome": "done", "reason": None, "next_step": "Ship it"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["outcome"] == "done"

    r = await client.post(
        "/feedback",
        json={"message": "Great app", "context": {"current_page": "/app", "last_sprint_id": sprint_id}},
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert "id" in r.json()

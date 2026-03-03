import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ui_login_sets_cookie_and_allows_app_page(client: AsyncClient):
    email = f"ui-{uuid.uuid4()}@example.com"
    password = "password"

    r = await client.post("/ui/register", data={"email": email, "password": password}, follow_redirects=False)
    assert r.status_code == 303
    assert "set-cookie" in r.headers

    cookie = r.headers["set-cookie"]
    assert "ui_access_token=" in cookie

    r2 = await client.get("/app", headers={"cookie": cookie})
    assert r2.status_code == 200
    assert "Tasks" in r2.text


@pytest.mark.asyncio
async def test_ui_htmx_create_task_renders_row(client: AsyncClient):
    email = f"ui-{uuid.uuid4()}@example.com"
    password = "password"

    r = await client.post("/ui/register", data={"email": email, "password": password}, follow_redirects=False)
    cookie = r.headers["set-cookie"]

    r2 = await client.post(
        "/app/tasks",
        data={"title": "My Task"},
        headers={"cookie": cookie, "hx-request": "true"},
    )
    assert r2.status_code == 200
    assert "My Task" in r2.text

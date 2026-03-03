import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ai_breakdown_fallback(client: AsyncClient, auth_headers: dict[str, str], monkeypatch):
    async def _fail(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr("app.services.llm._chat_completion_json", _fail)

    r = await client.post(
        "/ai/breakdown",
        json={"task_title": "Write README", "context": ""},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert "microsteps" in data
    assert isinstance(data["microsteps"], list)
    assert len(data["microsteps"]) > 0


@pytest.mark.asyncio
async def test_ai_rate_limit(client: AsyncClient, auth_headers: dict[str, str], monkeypatch):
    async def _ok(*args, **kwargs):
        return ["Open the doc"]

    monkeypatch.setattr("app.services.llm._chat_completion_json", _ok)

    for _ in range(30):
        r = await client.post(
            "/ai/breakdown",
            json={"task_title": "Write README"},
            headers=auth_headers,
        )
        assert r.status_code == 200

    r = await client.post(
        "/ai/breakdown",
        json={"task_title": "Write README"},
        headers=auth_headers,
    )
    assert r.status_code == 429
    assert r.json()["detail"] == "ai_rate_limited"

import uuid

import pytest
from httpx import AsyncClient

from app.core.settings import get_settings


@pytest.mark.asyncio
async def test_stripe_webhook_upgrades_user_to_pro_and_removes_ai_limit(client: AsyncClient):
    email = f"billing-{uuid.uuid4()}@example.com"
    password = "password"

    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201

    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Overrun the FREE limit (30/day)
    for _ in range(30):
        r = await client.post("/ai/breakdown", json={"task_title": "Write"}, headers=headers)
        assert r.status_code == 200

    r = await client.post("/ai/breakdown", json={"task_title": "Write"}, headers=headers)
    assert r.status_code == 429

    # Ensure webhook secret exists for route guard.
    import os

    os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
    get_settings.cache_clear()

    # Find the user id so we can map checkout session -> user.
    from sqlalchemy import select

    from app.db.models.user import User
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        user_row = (await session.execute(select(User).where(User.email == email.lower()))).scalar_one()
        user_id = str(user_row.id)

    def _fake_construct_event(*, payload: bytes, sig_header: str, secret: str):
        assert secret == "whsec_test"
        return {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_123",
                    "subscription": "sub_123",
                    "client_reference_id": user_id,
                }
            },
        }

    import app.api.routes.billing as billing_routes

    billing_routes.construct_event = _fake_construct_event  # type: ignore[assignment]

    r = await client.post(
        "/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "sig"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Should now be PRO -> no more rate limiting
    for _ in range(5):
        r = await client.post("/ai/breakdown", json={"task_title": "Write"}, headers=headers)
        assert r.status_code != 429

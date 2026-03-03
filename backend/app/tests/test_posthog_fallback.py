import os
import uuid

import pytest
from sqlalchemy import text

from sqlalchemy import select

from app.core.settings import get_settings
from app.db.models.user import User
from app.db.session import AsyncSessionLocal
from app.observability.analytics import track


@pytest.mark.asyncio
async def test_posthog_failure_does_not_break_and_db_event_is_inserted(monkeypatch):
    os.environ["POSTHOG_API_KEY"] = "ph_test"
    os.environ["POSTHOG_HOST"] = "https://app.posthog.com"
    get_settings.cache_clear()

    async def _fail_post(*args, **kwargs):
        raise RuntimeError("posthog_down")

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "post", _fail_post, raising=True)

    email = f"posthog-{uuid.uuid4()}@example.com"
    password = "password"

    async with AsyncSessionLocal() as session:
        from app.services.auth import register_user

        user = await register_user(db=session, email=email.lower(), password=password)
        user_id = user.id
        await track(user_id, "task_created", {"x": 1}, db=session)

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text("SELECT event_name FROM analytics_events WHERE user_id = :uid"),
                {"uid": user_id},
            )
        ).fetchall()
        names = [r[0] for r in rows]

    assert "task_created" in names

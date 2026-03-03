from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.models.analytics_event import AnalyticsEvent
from app.db.session import AsyncSessionLocal


async def track(
    user_id: UUID,
    event_name: str,
    props: dict[str, Any] | None = None,
    *,
    db: AsyncSession | None = None,
) -> None:
    settings = get_settings()
    event_props: dict[str, Any] = props or {}

    try:
        if db is not None:
            db.add(AnalyticsEvent(user_id=user_id, event_name=event_name, props=event_props))
            await db.commit()
        else:
            async with AsyncSessionLocal() as session:
                session.add(AnalyticsEvent(user_id=user_id, event_name=event_name, props=event_props))
                await session.commit()
    except Exception:
        return

    if not (settings.posthog_api_key and settings.posthog_host):
        return

    url = settings.posthog_host.rstrip("/") + "/capture"
    payload = {
        "api_key": settings.posthog_api_key,
        "event": event_name,
        "properties": {"distinct_id": str(user_id), **event_props},
        "timestamp": int(time.time()),
    }

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(url, json=payload)
    except Exception:
        return

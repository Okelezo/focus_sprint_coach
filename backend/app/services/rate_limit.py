from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_usage import AIUsage


class RateLimitError(Exception):
    pass


async def enforce_daily_ai_limit(*, db: AsyncSession, user_id: UUID, limit: int = 30) -> None:
    today = date.today()

    result = await db.execute(select(AIUsage).where(AIUsage.user_id == user_id, AIUsage.day == today))
    row = result.scalar_one_or_none()

    if row is None:
        row = AIUsage(user_id=user_id, day=today, calls=0)
        db.add(row)
        await db.flush()

    if row.calls >= limit:
        raise RateLimitError("ai_rate_limit_exceeded")

    row.calls += 1
    await db.commit()

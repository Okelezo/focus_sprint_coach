from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.feedback import Feedback


class FeedbackRateLimitError(Exception):
    pass


async def create_feedback(
    *,
    db: AsyncSession,
    user_id: UUID,
    message: str,
    context: dict,
) -> Feedback:
    now = datetime.now(timezone.utc)
    start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    count_result = await db.execute(
        select(func.count(Feedback.id)).where(
            Feedback.user_id == user_id,
            Feedback.created_at >= start,
            Feedback.created_at < end,
        )
    )
    used = int(count_result.scalar_one() or 0)
    if used >= 10:
        raise FeedbackRateLimitError("feedback_rate_limited")

    fb = Feedback(user_id=user_id, message=message, context=context or {})
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return fb

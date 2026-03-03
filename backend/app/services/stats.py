from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.sprint import Sprint
from app.schemas.sprint import StatsSummaryResponse


async def get_stats_summary(*, db: AsyncSession, user_id: UUID) -> StatsSummaryResponse:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=7)

    agg_result = await db.execute(
        select(
            func.count(Sprint.id),
            func.coalesce(func.sum(Sprint.duration_minutes), 0),
        ).where(Sprint.user_id == user_id, Sprint.started_at >= window_start)
    )
    sprint_count, minutes_sum = agg_result.one()

    days_result = await db.execute(
        select(func.date_trunc("day", Sprint.started_at))
        .where(Sprint.user_id == user_id)
        .group_by(func.date_trunc("day", Sprint.started_at))
        .order_by(func.date_trunc("day", Sprint.started_at).desc())
    )
    day_rows = [r[0].date() for r in days_result.all() if r[0] is not None]
    day_set = set(day_rows)

    streak = 0
    cursor = now.date()
    while cursor in day_set:
        streak += 1
        cursor = cursor - timedelta(days=1)

    return StatsSummaryResponse(
        days=7,
        total_sprints=int(sprint_count or 0),
        total_minutes=int(minutes_sum or 0),
        current_streak_days=streak,
    )

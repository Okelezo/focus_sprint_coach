from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.sprint import Sprint
from app.db.models.sprint_reflection import SprintReflection
from app.schemas.sprint import TodayHistoryResponse, SprintReflectionRead, TodayHistorySprint


async def get_today_history(*, db: AsyncSession, user_id: UUID) -> TodayHistoryResponse:
    now = datetime.now(timezone.utc)
    start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    sprints_result = await db.execute(
        select(Sprint)
        .where(Sprint.user_id == user_id, Sprint.started_at >= start, Sprint.started_at < end)
        .order_by(Sprint.started_at.desc())
    )
    sprints = list(sprints_result.scalars().all())

    reflections_result = await db.execute(
        select(SprintReflection)
        .join(Sprint, SprintReflection.sprint_id == Sprint.id)
        .where(Sprint.user_id == user_id, Sprint.started_at >= start, Sprint.started_at < end)
    )
    reflections = list(reflections_result.scalars().all())
    reflection_by_sprint_id = {r.sprint_id: r for r in reflections}

    return TodayHistoryResponse(
        date=start.date().isoformat(),
        sprints=[
            TodayHistorySprint(
                id=s.id,
                task_id=s.task_id,
                duration_minutes=s.duration_minutes,
                status=(s.status.value if hasattr(s.status, "value") else str(s.status)),
                started_at=s.started_at,
                ended_at=s.ended_at,
                reflection=(
                    SprintReflectionRead.model_validate(reflection_by_sprint_id[s.id])
                    if s.id in reflection_by_sprint_id
                    else None
                ),
            )
            for s in sprints
        ],
    )

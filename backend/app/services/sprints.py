from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.sprint import Sprint, SprintStatus
from app.db.models.sprint_event import SprintEvent, SprintEventType
from app.db.models.sprint_reflection import SprintReflection, SprintReflectionOutcome
from app.db.models.task import Task


async def start_sprint(
    *, db: AsyncSession, user_id: UUID, task_id: UUID | None, duration_minutes: int
) -> Sprint:
    if task_id is not None:
        task_result = await db.execute(select(Task).where(Task.user_id == user_id, Task.id == task_id))
        if task_result.scalar_one_or_none() is None:
            raise ValueError("task_not_found")

    sprint = Sprint(
        user_id=user_id,
        task_id=task_id,
        duration_minutes=duration_minutes,
        started_at=datetime.now(timezone.utc),
        status=SprintStatus.active.value,
    )
    db.add(sprint)
    await db.commit()
    await db.refresh(sprint)
    return sprint


async def add_sprint_event(
    *, db: AsyncSession, user_id: UUID, sprint_id: UUID, type: str, payload: dict
) -> SprintEvent:
    sprint_result = await db.execute(select(Sprint).where(Sprint.user_id == user_id, Sprint.id == sprint_id))
    sprint = sprint_result.scalar_one_or_none()
    if sprint is None:
        raise ValueError("sprint_not_found")

    event_type = SprintEventType(type).value
    event = SprintEvent(sprint_id=sprint_id, type=event_type, payload=payload or {})
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def finish_sprint(*, db: AsyncSession, user_id: UUID, sprint_id: UUID, status: str) -> Sprint:
    sprint_result = await db.execute(select(Sprint).where(Sprint.user_id == user_id, Sprint.id == sprint_id))
    sprint = sprint_result.scalar_one_or_none()
    if sprint is None:
        raise ValueError("sprint_not_found")

    sprint.status = SprintStatus(status).value
    sprint.ended_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sprint)
    return sprint


async def add_reflection(
    *,
    db: AsyncSession,
    user_id: UUID,
    sprint_id: UUID,
    outcome: str,
    reason: str | None,
    next_step: str | None,
) -> SprintReflection:
    sprint_result = await db.execute(select(Sprint).where(Sprint.user_id == user_id, Sprint.id == sprint_id))
    sprint = sprint_result.scalar_one_or_none()
    if sprint is None:
        raise ValueError("sprint_not_found")

    existing = await db.execute(select(SprintReflection).where(SprintReflection.sprint_id == sprint_id))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("reflection_already_exists")

    reflection = SprintReflection(
        sprint_id=sprint_id,
        outcome=SprintReflectionOutcome(outcome).value,
        reason=reason,
        next_step=next_step,
    )
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)
    return reflection

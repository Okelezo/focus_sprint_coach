from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
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


async def get_recent_sprint_stats(*, db: AsyncSession, user_id: UUID, days: int = 30) -> dict:
    """Get user's sprint statistics for the last N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Get sprints in time window
    sprints_result = await db.execute(
        select(Sprint)
        .where(Sprint.user_id == user_id, Sprint.started_at >= cutoff)
        .order_by(Sprint.started_at.desc())
    )
    sprints = list(sprints_result.scalars().all())
    
    if not sprints:
        return {
            "total_sprints": 0,
            "completion_rate": 0.0,
            "avg_duration_minutes": 25,
            "distraction_rate": 0.0,
        }
    
    # Get reflections for these sprints
    sprint_ids = [s.id for s in sprints]
    reflections_result = await db.execute(
        select(SprintReflection).where(SprintReflection.sprint_id.in_(sprint_ids))
    )
    reflections = list(reflections_result.scalars().all())
    reflection_by_sprint = {r.sprint_id: r for r in reflections}
    
    # Get distraction events
    events_result = await db.execute(
        select(SprintEvent)
        .where(
            SprintEvent.sprint_id.in_(sprint_ids),
            SprintEvent.type == SprintEventType.distraction.value,
        )
    )
    distraction_events = list(events_result.scalars().all())
    
    # Calculate stats
    total_sprints = len(sprints)
    completed = sum(
        1
        for s in sprints
        if s.id in reflection_by_sprint and reflection_by_sprint[s.id].outcome == "done"
    )
    completion_rate = completed / total_sprints if total_sprints > 0 else 0.0
    
    avg_duration = sum(s.duration_minutes for s in sprints) / total_sprints
    
    sprints_with_distractions = len(set(e.sprint_id for e in distraction_events))
    distraction_rate = sprints_with_distractions / total_sprints if total_sprints > 0 else 0.0
    
    return {
        "total_sprints": total_sprints,
        "completion_rate": completion_rate,
        "avg_duration_minutes": int(avg_duration),
        "distraction_rate": distraction_rate,
    }

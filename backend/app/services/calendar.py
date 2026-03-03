"""Calendar and task scheduling service."""

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.sprint import Sprint
from app.db.models.sprint_reflection import SprintReflection
from app.db.models.task import Task


async def get_tasks_for_date_range(
    *, db: AsyncSession, user_id: UUID, start_date: date, end_date: date
) -> list[Task]:
    """Get tasks scheduled within a date range or unscheduled tasks."""
    result = await db.execute(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.archived_at.is_(None),
            or_(
                and_(Task.scheduled_date >= start_date, Task.scheduled_date <= end_date),
                Task.scheduled_date.is_(None),
            ),
        )
        .order_by(Task.scheduled_date.asc().nullslast(), Task.created_at.desc())
    )
    return list(result.scalars().all())


async def get_tasks_for_date(*, db: AsyncSession, user_id: UUID, target_date: date) -> list[Task]:
    """Get tasks scheduled for a specific date."""
    result = await db.execute(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.archived_at.is_(None),
            Task.scheduled_date == target_date,
        )
        .order_by(Task.created_at.desc())
    )
    return list(result.scalars().all())


async def get_sprints_for_date(*, db: AsyncSession, user_id: UUID, target_date: date) -> list[Sprint]:
    """Get sprints that occurred on a specific date."""
    start = datetime(
        year=target_date.year,
        month=target_date.month,
        day=target_date.day,
        tzinfo=timezone.utc,
    )
    end = start + timedelta(days=1)

    result = await db.execute(
        select(Sprint)
        .where(Sprint.user_id == user_id, Sprint.started_at >= start, Sprint.started_at < end)
        .order_by(Sprint.started_at.desc())
    )
    return list(result.scalars().all())


async def schedule_task(
    *, db: AsyncSession, user_id: UUID, task_id: UUID, scheduled_date: date | None
) -> Task | None:
    """Schedule a task for a specific date (or unschedule if None)."""
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if task is None:
        return None

    task.scheduled_date = scheduled_date
    await db.commit()
    await db.refresh(task)
    return task


async def complete_task(*, db: AsyncSession, user_id: UUID, task_id: UUID) -> Task | None:
    """Mark a task as completed."""
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if task is None:
        return None

    task.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    return task


async def uncomplete_task(*, db: AsyncSession, user_id: UUID, task_id: UUID) -> Task | None:
    """Mark a task as not completed."""
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if task is None:
        return None

    task.completed_at = None
    await db.commit()
    await db.refresh(task)
    return task


async def get_week_overview(
    *, db: AsyncSession, user_id: UUID, week_start: date
) -> dict[str, dict]:
    """Get an overview of tasks and sprints for a week (7 days starting from week_start)."""
    week_end = week_start + timedelta(days=6)
    
    # Get all tasks in the week
    tasks = await get_tasks_for_date_range(
        db=db, user_id=user_id, start_date=week_start, end_date=week_end
    )
    
    # Group tasks by date
    tasks_by_date: dict[str, list[Task]] = {}
    for task in tasks:
        if task.scheduled_date:
            date_key = task.scheduled_date.isoformat()
            if date_key not in tasks_by_date:
                tasks_by_date[date_key] = []
            tasks_by_date[date_key].append(task)
    
    # Get sprint counts for each day
    sprint_counts: dict[str, int] = {}
    for i in range(7):
        day = week_start + timedelta(days=i)
        sprints = await get_sprints_for_date(db=db, user_id=user_id, target_date=day)
        sprint_counts[day.isoformat()] = len(sprints)
    
    # Build week overview
    week_data = {}
    for i in range(7):
        day = week_start + timedelta(days=i)
        date_key = day.isoformat()
        week_data[date_key] = {
            "date": day,
            "tasks": tasks_by_date.get(date_key, []),
            "sprint_count": sprint_counts.get(date_key, 0),
        }
    
    return week_data

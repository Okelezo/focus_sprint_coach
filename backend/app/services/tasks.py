from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.microstep import MicroStep
from app.db.models.task import Task


async def create_task(*, db: AsyncSession, user_id: UUID, title: str) -> Task:
    task = Task(user_id=user_id, title=title)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def list_tasks(*, db: AsyncSession, user_id: UUID) -> list[Task]:
    result = await db.execute(
        select(Task)
        .where(Task.user_id == user_id)
        .order_by(Task.created_at.desc())
    )
    return list(result.scalars().all())


async def get_task_detail(*, db: AsyncSession, user_id: UUID, task_id: UUID) -> Task | None:
    result = await db.execute(
        select(Task)
        .where(Task.user_id == user_id, Task.id == task_id)
        .options(selectinload(Task.microsteps))
    )
    return result.scalar_one_or_none()


async def add_microstep(*, db: AsyncSession, user_id: UUID, task_id: UUID, text: str, order_index: int) -> MicroStep:
    task_result = await db.execute(select(Task).where(Task.user_id == user_id, Task.id == task_id))
    task = task_result.scalar_one_or_none()
    if task is None:
        raise ValueError("task_not_found")

    microstep = MicroStep(task_id=task_id, text=text, order_index=order_index)
    db.add(microstep)
    await db.commit()
    await db.refresh(microstep)
    return microstep

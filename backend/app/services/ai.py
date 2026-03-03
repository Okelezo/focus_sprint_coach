import time
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.microstep import MicroStep
from app.db.models.sprint import Sprint
from app.db.models.sprint_event import SprintEvent, SprintEventType
from app.db.models.task import Task
from app.observability.analytics import track
from app.core.settings import get_settings
from app.services.llm import LLMError, generate_microsteps, generate_next_step_from_reflection
from app.services.rate_limit import enforce_daily_ai_limit
from app.services.subscriptions import FREE, get_effective_plan


def _heuristic_microsteps(task_title: str) -> list[str]:
    base = task_title.strip() or "the task"
    return [
        "Open your notes app",
        f"Write 2 bullets about what 'done' looks like for {base}",
        "Write 3 tiny sub-tasks (1-5 min each)",
        "Pick the easiest sub-task and start it",
    ][:7]


async def breakdown_task(
    *, db: AsyncSession, user_id: UUID, task_id: UUID | None, task_title: str, context: str | None
) -> list[str]:
    plan = await get_effective_plan(db=db, user_id=user_id)
    if plan == FREE:
        await enforce_daily_ai_limit(db=db, user_id=user_id)

    settings = get_settings()

    started = time.perf_counter()
    success = True
    tokens: int | None = None

    previous_steps: list[str] = []
    if task_id is not None:
        prev_result = await db.execute(
            select(MicroStep.text).where(MicroStep.task_id == task_id).order_by(MicroStep.order_index)
        )
        previous_steps = list(prev_result.scalars().all())

    steps: list[str]
    try:
        steps = await generate_microsteps(task_title=task_title, context=context, previous_steps=previous_steps)
        if not steps:
            if settings.ai_strict:
                raise LLMError("empty_output")
            success = False
            steps = _heuristic_microsteps(task_title)
    except (LLMError, Exception):  # noqa: BLE001
        if settings.ai_strict:
            raise
        success = False
        steps = _heuristic_microsteps(task_title)

    latency_ms = int((time.perf_counter() - started) * 1000)
    await track(
        user_id,
        "ai_breakdown_called",
        {
            "task_id": str(task_id) if task_id is not None else None,
            "success": success,
            "latency_ms": latency_ms,
            "tokens": tokens,
        },
        db=db,
    )

    if task_id is not None:
        max_idx_result = await db.execute(
            select(func.coalesce(func.max(MicroStep.order_index), 0)).where(MicroStep.task_id == task_id)
        )
        max_idx = int(max_idx_result.scalar_one() or 0)

        for i, text in enumerate(steps, start=1):
            db.add(MicroStep(task_id=task_id, text=text, order_index=max_idx + i))
        await db.commit()

    return steps


async def blocker_recovery(
    *, db: AsyncSession, user_id: UUID, sprint_id: UUID, blocker: str
) -> dict:
    plan = await get_effective_plan(db=db, user_id=user_id)
    if plan == FREE:
        await enforce_daily_ai_limit(db=db, user_id=user_id)

    settings = get_settings()

    sprint_result = await db.execute(select(Sprint).where(Sprint.user_id == user_id, Sprint.id == sprint_id))
    sprint = sprint_result.scalar_one_or_none()
    if sprint is None:
        raise ValueError("sprint_not_found")

    task_title = "Untitled task"
    if sprint.task_id:
        task_result = await db.execute(select(Task).where(Task.id == sprint.task_id))
        task = task_result.scalar_one_or_none()
        if task is not None:
            task_title = task.title

    await db.execute(
        select(SprintEvent).where(SprintEvent.sprint_id == sprint_id).limit(1)
    )
    db.add(
        SprintEvent(
            sprint_id=sprint_id,
            type=SprintEventType.blocker,
            payload={"blocker": blocker},
        )
    )
    await db.commit()

    try:
        unblock_steps = await generate_microsteps(
            task_title=f"Unblock: {blocker}",
            context=f"Original task: {task_title}",
        )
    except (LLMError, Exception):  # noqa: BLE001
        unblock_steps = [
            "Write the blocker in 1 sentence",
            "List 2 ways to reduce the blocker",
            "Ask 1 specific question to the right person/tool",
        ]

    try:
        progress_anyway_steps = await generate_microsteps(
            task_title=f"Make progress anyway on: {task_title}",
            context=f"Blocker: {blocker}",
        )
    except (LLMError, Exception):  # noqa: BLE001
        progress_anyway_steps = [
            "Open the task doc",
            "Write 2 bullets of what you can do without the blocker",
            "Do the smallest available sub-task",
        ]

    reflection = {"blocker": blocker, "task_title": task_title}
    try:
        suggested_next_step = await generate_next_step_from_reflection(task_title=task_title, reflection=reflection)
    except (LLMError, Exception):  # noqa: BLE001
        if settings.ai_strict:
            raise
        suggested_next_step = "Write 1 sentence clarifying what you need next"

    return {
        "unblock_steps": unblock_steps[:7],
        "progress_anyway_steps": progress_anyway_steps[:7],
        "suggested_next_step": suggested_next_step,
    }

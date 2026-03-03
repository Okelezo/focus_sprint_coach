from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.observability.analytics import track
from app.schemas.microstep import MicroStepCreate, MicroStepRead
from app.schemas.task import TaskCreate, TaskDetail, TaskRead
from app.services.tasks import add_microstep, create_task, get_task_detail, list_tasks

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRead:
    task = await create_task(db=db, user_id=current_user.id, title=payload.title)
    await track(current_user.id, "task_created", {"task_id": str(task.id)}, db=db)
    return TaskRead.model_validate(task)


@router.get("", response_model=list[TaskRead])
async def list_(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TaskRead]:
    tasks = await list_tasks(db=db, user_id=current_user.id)
    return [TaskRead.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskDetail)
async def detail(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskDetail:
    task = await get_task_detail(db=db, user_id=current_user.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return TaskDetail.model_validate(task)


@router.post("/{task_id}/microsteps", response_model=MicroStepRead, status_code=status.HTTP_201_CREATED)
async def add_step(
    task_id: UUID,
    payload: MicroStepCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MicroStepRead:
    try:
        step = await add_microstep(
            db=db,
            user_id=current_user.id,
            task_id=task_id,
            text=payload.text,
            order_index=payload.order_index,
        )
        return MicroStepRead.model_validate(step)
    except ValueError as e:
        if str(e) == "task_not_found":
            raise HTTPException(status_code=404, detail="task_not_found")
        raise

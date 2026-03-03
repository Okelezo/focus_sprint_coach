from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.task import Task
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.ai import (
    AIBlockerRecoveryRequest,
    AIBlockerRecoveryResponse,
    AIBreakdownRequest,
    AIBreakdownResponse,
)
from app.services.ai import blocker_recovery, breakdown_task
from app.services.llm import LLMError
from app.services.rate_limit import RateLimitError

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/breakdown", response_model=AIBreakdownResponse, response_model_exclude_none=True)
async def breakdown(
    payload: AIBreakdownRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIBreakdownResponse:
    task_title = payload.task_title

    if payload.task_id is not None:
        task_result = await db.execute(
            select(Task).where(Task.user_id == current_user.id, Task.id == payload.task_id)
        )
        task = task_result.scalar_one_or_none()
        if task is None:
            raise HTTPException(status_code=404, detail="task_not_found")
        task_title = task.title

    if not task_title:
        raise HTTPException(status_code=400, detail="task_title_or_task_id_required")

    try:
        steps = await breakdown_task(
            db=db,
            user_id=current_user.id,
            task_id=payload.task_id,
            task_title=task_title,
            context=payload.context,
        )
    except RateLimitError:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="ai_rate_limited")
    except LLMError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    return AIBreakdownResponse(task_id=payload.task_id, microsteps=steps)


@router.post("/blocker_recovery", response_model=AIBlockerRecoveryResponse)
async def recover(
    payload: AIBlockerRecoveryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIBlockerRecoveryResponse:
    try:
        result = await blocker_recovery(
            db=db,
            user_id=current_user.id,
            sprint_id=payload.sprint_id,
            blocker=payload.blocker,
        )
    except RateLimitError:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="ai_rate_limited")
    except LLMError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except ValueError as e:
        if str(e) == "sprint_not_found":
            raise HTTPException(status_code=404, detail="sprint_not_found")
        raise

    return AIBlockerRecoveryResponse(**result)

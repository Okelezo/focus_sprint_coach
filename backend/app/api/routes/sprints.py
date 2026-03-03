from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.observability.analytics import track
from app.schemas.sprint import (
    SprintEventCreate,
    SprintEventRead,
    SprintFinishRequest,
    SprintRead,
    SprintReflectionCreate,
    SprintReflectionRead,
    SprintStartRequest,
)
from app.services.sprints import add_reflection, add_sprint_event, finish_sprint, start_sprint

router = APIRouter(prefix="/sprints", tags=["sprints"])


@router.post("/start", response_model=SprintRead, status_code=status.HTTP_201_CREATED)
async def start(
    payload: SprintStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SprintRead:
    try:
        sprint = await start_sprint(
            db=db,
            user_id=current_user.id,
            task_id=payload.task_id,
            duration_minutes=payload.duration_minutes,
        )
        await track(
            current_user.id,
            "sprint_started",
            {"sprint_id": str(sprint.id), "duration_minutes": sprint.duration_minutes},
            db=db,
        )
        return SprintRead.model_validate(sprint)
    except ValueError as e:
        if str(e) == "task_not_found":
            raise HTTPException(status_code=404, detail="task_not_found")
        raise


@router.post("/{sprint_id}/events", response_model=SprintEventRead, status_code=status.HTTP_201_CREATED)
async def event(
    sprint_id: UUID,
    payload: SprintEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SprintEventRead:
    try:
        ev = await add_sprint_event(
            db=db,
            user_id=current_user.id,
            sprint_id=sprint_id,
            type=payload.type,
            payload=payload.payload,
        )
        await track(
            current_user.id,
            "sprint_event_logged",
            {"sprint_id": str(sprint_id), "type": payload.type},
            db=db,
        )
        return SprintEventRead.model_validate(ev)
    except ValueError as e:
        if str(e) == "sprint_not_found":
            raise HTTPException(status_code=404, detail="sprint_not_found")
        raise


@router.post("/{sprint_id}/finish", response_model=SprintRead)
async def finish(
    sprint_id: UUID,
    payload: SprintFinishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SprintRead:
    try:
        sprint = await finish_sprint(db=db, user_id=current_user.id, sprint_id=sprint_id, status=payload.status)
        await track(
            current_user.id,
            "sprint_finished",
            {"sprint_id": str(sprint_id), "status": payload.status},
            db=db,
        )
        return SprintRead.model_validate(sprint)
    except ValueError as e:
        if str(e) == "sprint_not_found":
            raise HTTPException(status_code=404, detail="sprint_not_found")
        raise


@router.post("/{sprint_id}/reflection", response_model=SprintReflectionRead, status_code=status.HTTP_201_CREATED)
async def reflect(
    sprint_id: UUID,
    payload: SprintReflectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SprintReflectionRead:
    try:
        reflection = await add_reflection(
            db=db,
            user_id=current_user.id,
            sprint_id=sprint_id,
            outcome=payload.outcome,
            reason=payload.reason,
            next_step=payload.next_step,
        )
        await track(
            current_user.id,
            "reflection_saved",
            {"sprint_id": str(sprint_id), "outcome": payload.outcome},
            db=db,
        )
        return SprintReflectionRead.model_validate(reflection)
    except ValueError as e:
        if str(e) == "sprint_not_found":
            raise HTTPException(status_code=404, detail="sprint_not_found")
        if str(e) == "reflection_already_exists":
            raise HTTPException(status_code=400, detail="reflection_already_exists")
        raise

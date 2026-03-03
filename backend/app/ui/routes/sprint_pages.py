from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.sprint import Sprint, SprintStatus
from app.db.session import get_db
from app.observability.analytics import track
from app.services.sprints import add_reflection, add_sprint_event, finish_sprint, start_sprint
from app.services.tasks import list_tasks
from app.ui.deps import get_current_user_from_cookie
from app.ui.templates import templates

router = APIRouter(prefix="/app", tags=["ui"])


@router.get("/sprint", response_class=HTMLResponse)
async def sprint_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    tasks = await list_tasks(db=db, user_id=user.id)

    active_result = await db.execute(
        select(Sprint)
        .where(Sprint.user_id == user.id, Sprint.status == SprintStatus.active)
        .order_by(Sprint.started_at.desc())
    )
    active = active_result.scalars().first()

    return templates.TemplateResponse(
        "sprint.html",
        {"request": request, "user": user, "tasks": tasks, "active": active},
    )


@router.post("/sprint/start")
async def ui_start_sprint(
    request: Request,
    duration_minutes: int = Form(...),
    task_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
):
    task_uuid = UUID(task_id) if task_id else None
    sprint = await start_sprint(db=db, user_id=user.id, task_id=task_uuid, duration_minutes=duration_minutes)
    await track(
        user.id,
        "sprint_started",
        {"sprint_id": str(sprint.id), "duration_minutes": sprint.duration_minutes},
        db=db,
    )
    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app/sprint", status_code=303)
    return templates.TemplateResponse(
        "partials/sprint_active.html",
        {"request": request, "sprint": sprint, "duration_minutes": duration_minutes},
    )


@router.post("/sprint/{sprint_id}/distraction")
async def ui_distraction_note(
    request: Request,
    sprint_id: UUID,
    note: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
):
    await add_sprint_event(
        db=db,
        user_id=user.id,
        sprint_id=sprint_id,
        type="distraction",
        payload={"note": note},
    )
    await track(
        user.id,
        "sprint_event_logged",
        {"sprint_id": str(sprint_id), "type": "distraction"},
        db=db,
    )
    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app/sprint", status_code=303)
    return templates.TemplateResponse(
        "partials/sprint_note_row.html",
        {"request": request, "note": note},
    )


@router.post("/sprint/{sprint_id}/finish")
async def ui_finish_sprint(
    request: Request,
    sprint_id: UUID,
    status: str = Form("completed"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
):
    sprint = await finish_sprint(db=db, user_id=user.id, sprint_id=sprint_id, status=status)
    await track(user.id, "sprint_finished", {"sprint_id": str(sprint_id), "status": status}, db=db)
    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app/sprint", status_code=303)
    return templates.TemplateResponse(
        "partials/sprint_reflection_form.html",
        {"request": request, "sprint": sprint},
    )


@router.post("/sprint/{sprint_id}/reflection")
async def ui_reflection(
    request: Request,
    sprint_id: UUID,
    outcome: str = Form(...),
    reason: str = Form(""),
    next_step: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
):
    try:
        await add_reflection(
            db=db,
            user_id=user.id,
            sprint_id=sprint_id,
            outcome=outcome,
            reason=reason or None,
            next_step=next_step or None,
        )
        await track(user.id, "reflection_saved", {"sprint_id": str(sprint_id), "outcome": outcome}, db=db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app/sprint", status_code=303)
    return templates.TemplateResponse(
        "partials/sprint_done.html",
        {"request": request},
    )

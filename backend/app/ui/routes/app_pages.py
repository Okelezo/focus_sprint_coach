from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models.sprint import Sprint
from app.services.ai import breakdown_task
from app.services.calendar import (
    complete_task,
    get_sprints_for_date,
    get_tasks_for_date,
    get_week_overview,
    schedule_task,
    uncomplete_task,
)
from app.services.history import get_today_history
from app.services.tasks import create_task, get_task_detail, list_tasks
from app.observability.analytics import track
from app.services.feedback import FeedbackRateLimitError, create_feedback
from app.ui.deps import get_current_user_from_cookie
from app.ui.templates import templates

router = APIRouter(prefix="/app", tags=["ui"])


@router.get("", response_class=HTMLResponse)
async def app_home(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    tasks = await list_tasks(db=db, user_id=user.id)
    return templates.TemplateResponse("app.html", {"request": request, "user": user, "tasks": tasks})


@router.post("/tasks")
async def ui_create_task(
    request: Request,
    title: str = Form(...),
    scheduled_date: str = Form(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
):
    task = await create_task(db=db, user_id=user.id, title=title)
    
    # Schedule task if date provided
    if scheduled_date:
        try:
            target_date = date.fromisoformat(scheduled_date)
            await schedule_task(db=db, user_id=user.id, task_id=task.id, scheduled_date=target_date)
            await db.refresh(task)
        except ValueError:
            pass
    
    await track(user.id, "task_created", {"task_id": str(task.id)}, db=db)
    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app", status_code=303)
    return templates.TemplateResponse(
        "partials/task_row.html",
        {"request": request, "task": task},
    )


@router.get("/task/{task_id}", response_class=HTMLResponse)
async def task_detail(
    request: Request,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    task = await get_task_detail(db=db, user_id=user.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return templates.TemplateResponse("task_detail.html", {"request": request, "user": user, "task": task})


@router.post("/task/{task_id}/generate_microsteps")
async def generate_microsteps(
    request: Request,
    task_id: UUID,
    context: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
):
    task = await get_task_detail(db=db, user_id=user.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    await breakdown_task(db=db, user_id=user.id, task_id=task_id, task_title=task.title, context=context)

    task = await get_task_detail(db=db, user_id=user.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    if not request.headers.get("HX-Request"):
        return RedirectResponse(url=f"/app/task/{task_id}", status_code=303)
    return templates.TemplateResponse(
        "partials/microsteps_list.html",
        {"request": request, "task": task},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def app_calendar(
    request: Request,
    target_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    # Parse target date or default to today
    if target_date:
        try:
            selected_date = date.fromisoformat(target_date)
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()

    # Get week start (Monday)
    week_start = selected_date - timedelta(days=selected_date.weekday())
    week_overview = await get_week_overview(db=db, user_id=user.id, week_start=week_start)

    # Get tasks and sprints for selected date
    tasks = await get_tasks_for_date(db=db, user_id=user.id, target_date=selected_date)
    sprints = await get_sprints_for_date(db=db, user_id=user.id, target_date=selected_date)

    await track(user.id, "calendar_viewed", {"date": selected_date.isoformat()}, db=db)
    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "user": user,
            "selected_date": selected_date,
            "week_start": week_start,
            "week_overview": week_overview,
            "tasks": tasks,
            "sprints": sprints,
            "timedelta": timedelta,
            "date": date,
        },
    )


@router.get("/history", response_class=HTMLResponse)
async def app_history(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    today = await get_today_history(db=db, user_id=user.id)
    await track(user.id, "history_viewed", {"date": today.date}, db=db)
    return templates.TemplateResponse(
        "history.html",
        {"request": request, "user": user, "today": today},
    )


@router.get("/feedback", response_class=HTMLResponse)
async def feedback_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    referer = request.headers.get("referer")
    current_page = referer or str(request.url_for("app_home"))

    last_sprint_id: str | None = None
    result = await db.execute(
        select(Sprint.id).where(Sprint.user_id == user.id).order_by(Sprint.started_at.desc()).limit(1)
    )
    last = result.scalar_one_or_none()
    if last is not None:
        last_sprint_id = str(last)

    return templates.TemplateResponse(
        "feedback.html",
        {
            "request": request,
            "user": user,
            "current_page": current_page,
            "last_sprint_id": last_sprint_id,
        },
    )


@router.post("/feedback", response_class=HTMLResponse)
async def submit_feedback(
    request: Request,
    message: str = Form(...),
    current_page: str = Form(""),
    last_sprint_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    context = {
        "current_page": current_page,
        "last_sprint_id": last_sprint_id or None,
    }

    try:
        await create_feedback(db=db, user_id=user.id, message=message, context=context)
    except FeedbackRateLimitError:
        return templates.TemplateResponse(
            "feedback.html",
            {
                "request": request,
                "user": user,
                "current_page": current_page,
                "last_sprint_id": last_sprint_id or None,
                "error": "feedback_rate_limited",
            },
            status_code=429,
        )

    return templates.TemplateResponse(
        "feedback.html",
        {
            "request": request,
            "user": user,
            "current_page": current_page,
            "last_sprint_id": last_sprint_id or None,
            "ok": True,
        },
    )


@router.post("/task/{task_id}/schedule", response_class=HTMLResponse)
async def schedule_task_endpoint(
    request: Request,
    task_id: UUID,
    scheduled_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    target_date = date.fromisoformat(scheduled_date) if scheduled_date else None
    task = await schedule_task(db=db, user_id=user.id, task_id=task_id, scheduled_date=target_date)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    await track(user.id, "task_scheduled", {"task_id": str(task_id), "date": scheduled_date}, db=db)
    
    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app/calendar", status_code=303)
    return templates.TemplateResponse(
        "partials/task_row.html",
        {"request": request, "task": task},
    )


@router.post("/task/{task_id}/complete", response_class=HTMLResponse)
async def complete_task_endpoint(
    request: Request,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    task = await complete_task(db=db, user_id=user.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    await track(user.id, "task_completed", {"task_id": str(task_id)}, db=db)
    
    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app/calendar", status_code=303)
    return templates.TemplateResponse(
        "partials/task_row.html",
        {"request": request, "task": task},
    )


@router.post("/task/{task_id}/uncomplete", response_class=HTMLResponse)
async def uncomplete_task_endpoint(
    request: Request,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    task = await uncomplete_task(db=db, user_id=user.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")

    await track(user.id, "task_uncompleted", {"task_id": str(task_id)}, db=db)
    
    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app/calendar", status_code=303)
    return templates.TemplateResponse(
        "partials/task_row.html",
        {"request": request, "task": task},
    )

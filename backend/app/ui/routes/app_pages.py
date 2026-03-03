from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models.sprint import Sprint
from app.services.ai import breakdown_task
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
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
):
    task = await create_task(db=db, user_id=user.id, title=title)
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

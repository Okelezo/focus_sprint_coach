"""UI routes for orchestrator-powered sprint coaching."""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.orchestrator import (
    analyze_task_clarity,
    pick_best_next_action,
    triage_distraction,
    generate_reflection,
    _get_user_context,
)
from app.services.adaptive_engine import recommend_sprint_duration, detect_task_paralysis
from app.services.ai import breakdown_task
from app.services.tasks import get_task_detail
from app.observability.analytics import track
from app.ui.deps import get_current_user_from_cookie
from app.ui.templates import templates

router = APIRouter(prefix="/app/orchestrator", tags=["ui-orchestrator"])


@router.post("/prepare-sprint", response_class=HTMLResponse)
async def prepare_sprint(
    request: Request,
    task_id: UUID = Form(...),
    context: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    """Prepare for sprint with orchestrator guidance - analyze task and generate recommendations."""
    
    # Get task details
    task = await get_task_detail(db=db, user_id=user.id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    
    # Analyze if task needs clarification
    clarity_analysis = await analyze_task_clarity(task_title=task.title, context=context or None)
    
    # If needs clarification, show questions
    if clarity_analysis.get("needs_clarification") and clarity_analysis.get("questions"):
        await track(user.id, "orchestrator_needs_clarification", {"task_id": str(task_id)}, db=db)
        return templates.TemplateResponse(
            "partials/orchestrator_clarification.html",
            {
                "request": request,
                "task": task,
                "questions": clarity_analysis["questions"],
                "reasoning": clarity_analysis["reasoning"],
            },
        )
    
    # Generate microsteps and pick best next action
    microsteps = await breakdown_task(
        db=db,
        user_id=user.id,
        task_id=task_id,
        task_title=task.title,
        context=context or None,
    )
    
    user_context = await _get_user_context(db=db, user_id=user.id)
    
    recommendation = await pick_best_next_action(
        task_title=task.title,
        microsteps=microsteps,
        user_context=user_context,
    )
    
    # Get adaptive duration recommendation
    duration_rec = await recommend_sprint_duration(db=db, user_id=user.id)
    
    # Check for task paralysis
    paralysis = await detect_task_paralysis(db=db, user_id=user.id, task_id=task_id)
    
    await track(user.id, "orchestrator_prepared_sprint", {"task_id": str(task_id), "paralysis": paralysis["is_paralyzed"]}, db=db)
    
    # Return recommendation with option to start sprint
    return templates.TemplateResponse(
        "partials/orchestrator_sprint_ready.html",
        {
            "request": request,
            "task": task,
            "recommendation": {
                **recommendation,
                "microsteps": microsteps,
            },
            "suggested_duration": duration_rec["recommended_duration"],
            "duration_reasoning": duration_rec["reasoning"],
            "paralysis": paralysis,
        },
    )


@router.post("/triage-distraction-ui", response_class=HTMLResponse)
async def triage_distraction_ui(
    request: Request,
    distraction_note: str = Form(...),
    task_title: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    """Triage a distraction and show recovery suggestion."""
    
    result = await triage_distraction(
        distraction_note=distraction_note,
        task_title=task_title,
    )
    
    await track(user.id, "orchestrator_triaged_distraction", {"urgency": result["urgency"]}, db=db)
    
    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app/sprint", status_code=303)
    
    return templates.TemplateResponse(
        "partials/orchestrator_distraction_triage.html",
        {
            "request": request,
            "triage": result,
            "distraction_note": distraction_note,
        },
    )


@router.post("/auto-reflect", response_class=HTMLResponse)
async def auto_reflect(
    request: Request,
    task_title: str = Form(...),
    duration_minutes: int = Form(...),
    distractions: str = Form(""),  # Comma-separated
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    """Auto-generate sprint reflection."""
    
    distraction_list = [d.strip() for d in distractions.split(",") if d.strip()]
    user_context = await _get_user_context(db=db, user_id=user.id)
    
    result = await generate_reflection(
        task_title=task_title,
        duration_minutes=duration_minutes,
        distractions=distraction_list,
        user_context=user_context,
    )
    
    await track(user.id, "orchestrator_auto_reflected", {"outcome": result["outcome"]}, db=db)
    
    if not request.headers.get("HX-Request"):
        return RedirectResponse(url="/app/sprint", status_code=303)
    
    return templates.TemplateResponse(
        "partials/orchestrator_reflection.html",
        {
            "request": request,
            "reflection": result,
        },
    )

"""Orchestrator API endpoints for agentic sprint coaching."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import get_current_user
from app.db.models.user import User
from app.services.orchestrator import (
    analyze_task_clarity,
    generate_reflection,
    pick_best_next_action,
    propose_next_sprint,
    triage_distraction,
    _get_user_context,
)
from app.services.ai import breakdown_task
from app.observability.analytics import track


router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class AnalyzeTaskRequest(BaseModel):
    task_title: str
    context: str | None = None


class AnalyzeTaskResponse(BaseModel):
    needs_clarification: bool
    questions: list[str]
    reasoning: str


class PickNextActionRequest(BaseModel):
    task_title: str
    task_id: UUID | None = None
    context: str | None = None


class PickNextActionResponse(BaseModel):
    recommended_step: str
    reasoning: str
    estimated_minutes: int
    microsteps: list[str]


class TriageDistractionRequest(BaseModel):
    distraction_note: str
    task_title: str


class TriageDistractionResponse(BaseModel):
    urgency: str
    action: str
    reasoning: str


class GenerateReflectionRequest(BaseModel):
    task_title: str
    duration_minutes: int
    distractions: list[str]


class GenerateReflectionResponse(BaseModel):
    outcome: str
    reason: str
    next_step: str


class ProposeNextSprintRequest(BaseModel):
    current_task_id: UUID | None = None
    last_reflection: dict


class ProposeNextSprintResponse(BaseModel):
    task_id: UUID | None
    task_title: str
    reasoning: str
    suggested_duration: int


@router.post("/analyze-task", response_model=AnalyzeTaskResponse)
async def analyze_task_endpoint(
    request: AnalyzeTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Analyze if a task needs clarification before starting sprint."""
    result = await analyze_task_clarity(task_title=request.task_title, context=request.context)
    await track(current_user.id, "orchestrator_analyze_task", {"needs_clarification": result["needs_clarification"]}, db=db)
    return result


@router.post("/pick-next-action", response_model=PickNextActionResponse)
async def pick_next_action_endpoint(
    request: PickNextActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate microsteps and pick the best one to start with."""
    # Generate microsteps first
    microsteps = await breakdown_task(
        db=db,
        user_id=current_user.id,
        task_id=request.task_id,
        task_title=request.task_title,
        context=request.context,
    )
    
    # Get user context for personalization
    user_context = await _get_user_context(db=db, user_id=current_user.id)
    
    # Pick best next action
    result = await pick_best_next_action(
        task_title=request.task_title,
        microsteps=microsteps,
        user_context=user_context,
    )
    
    await track(current_user.id, "orchestrator_pick_action", {"task_id": str(request.task_id) if request.task_id else None}, db=db)
    
    return {
        **result,
        "microsteps": microsteps,
    }


@router.post("/triage-distraction", response_model=TriageDistractionResponse)
async def triage_distraction_endpoint(
    request: TriageDistractionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Triage a distraction and suggest minimal recovery action."""
    result = await triage_distraction(
        distraction_note=request.distraction_note,
        task_title=request.task_title,
    )
    await track(current_user.id, "orchestrator_triage_distraction", {"urgency": result["urgency"]}, db=db)
    return result


@router.post("/generate-reflection", response_model=GenerateReflectionResponse)
async def generate_reflection_endpoint(
    request: GenerateReflectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Auto-generate sprint reflection based on what happened."""
    user_context = await _get_user_context(db=db, user_id=current_user.id)
    
    result = await generate_reflection(
        task_title=request.task_title,
        duration_minutes=request.duration_minutes,
        distractions=request.distractions,
        user_context=user_context,
    )
    
    await track(current_user.id, "orchestrator_generate_reflection", {"outcome": result["outcome"]}, db=db)
    return result


@router.post("/propose-next-sprint", response_model=ProposeNextSprintResponse)
async def propose_next_sprint_endpoint(
    request: ProposeNextSprintRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Propose what to work on next based on reflection and patterns."""
    result = await propose_next_sprint(
        db=db,
        user_id=current_user.id,
        current_task_id=request.current_task_id,
        last_reflection=request.last_reflection,
    )
    
    await track(current_user.id, "orchestrator_propose_sprint", {"task_id": str(result["task_id"]) if result["task_id"] else None}, db=db)
    return result

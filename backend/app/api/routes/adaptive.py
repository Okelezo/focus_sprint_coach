"""Adaptive Engine and Weekly Review API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import get_current_user
from app.db.models.user import User
from app.services.adaptive_engine import (
    analyze_time_of_day_patterns,
    detect_task_paralysis,
    get_adaptive_recommendations,
    recommend_sprint_duration,
)
from app.services.weekly_review import get_weekly_review, generate_weekly_summary, suggest_weekly_experiment
from app.observability.analytics import track


router = APIRouter(prefix="/adaptive", tags=["adaptive"])


class DurationRecommendationResponse(BaseModel):
    recommended_duration: int
    reasoning: str
    confidence: float


class TaskParalysisResponse(BaseModel):
    is_paralyzed: bool
    indicators: list[str]
    suggestion: str


class TimeOfDayResponse(BaseModel):
    best_hours: list[int]
    worst_hours: list[int]
    recommendation: str
    sample_size: int


class AdaptiveRecommendationsResponse(BaseModel):
    duration: DurationRecommendationResponse
    time_of_day: TimeOfDayResponse
    task_paralysis: TaskParalysisResponse | None = None


class WeeklySummaryResponse(BaseModel):
    week_start: str
    week_end: str
    total_sprints: int
    total_minutes: int
    completion_rate: float
    top_outcomes: dict
    distraction_count: int
    most_productive_day: str
    task_breakdown: dict
    patterns: list[str]
    shareable_stat: str


class ExperimentResponse(BaseModel):
    experiment: str
    reasoning: str
    how_to_measure: str


class WeeklyReviewResponse(BaseModel):
    summary: WeeklySummaryResponse
    experiment: ExperimentResponse
    week_label: str


@router.get("/duration-recommendation", response_model=DurationRecommendationResponse)
async def get_duration_recommendation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get personalized sprint duration recommendation."""
    result = await recommend_sprint_duration(db=db, user_id=current_user.id)
    await track(current_user.id, "adaptive_duration_recommendation", {"duration": result["recommended_duration"]}, db=db)
    return result


@router.get("/task-paralysis/{task_id}", response_model=TaskParalysisResponse)
async def check_task_paralysis(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if user is stuck on a task."""
    result = await detect_task_paralysis(db=db, user_id=current_user.id, task_id=task_id)
    await track(current_user.id, "adaptive_paralysis_check", {"task_id": str(task_id), "is_paralyzed": result["is_paralyzed"]}, db=db)
    return result


@router.get("/time-of-day", response_model=TimeOfDayResponse)
async def get_time_of_day_analysis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get time-of-day productivity analysis."""
    result = await analyze_time_of_day_patterns(db=db, user_id=current_user.id)
    await track(current_user.id, "adaptive_time_analysis", {"sample_size": result["sample_size"]}, db=db)
    return result


@router.get("/recommendations", response_model=AdaptiveRecommendationsResponse)
async def get_all_recommendations(
    task_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all adaptive recommendations in one call."""
    result = await get_adaptive_recommendations(db=db, user_id=current_user.id, task_id=task_id)
    await track(current_user.id, "adaptive_recommendations_viewed", {"has_task": task_id is not None}, db=db)
    return result


@router.get("/weekly-review", response_model=WeeklyReviewResponse)
async def get_weekly_review_endpoint(
    week_offset: int = Query(0, description="0 for current week, -1 for last week"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get comprehensive weekly review with patterns and experiment."""
    result = await get_weekly_review(db=db, user_id=current_user.id, week_offset=week_offset)
    await track(current_user.id, "weekly_review_viewed", {"week_offset": week_offset}, db=db)
    return result


@router.get("/weekly-summary", response_model=WeeklySummaryResponse)
async def get_weekly_summary_endpoint(
    week_offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get weekly summary only."""
    result = await generate_weekly_summary(db=db, user_id=current_user.id, week_offset=week_offset)
    await track(current_user.id, "weekly_summary_viewed", {"week_offset": week_offset}, db=db)
    return result

"""UI routes for adaptive features and weekly review."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.weekly_review import get_weekly_review
from app.services.adaptive_engine import get_adaptive_recommendations
from app.observability.analytics import track
from app.ui.deps import get_current_user_from_cookie
from app.ui.templates import templates

router = APIRouter(prefix="/app", tags=["ui-adaptive"])


@router.get("/weekly-review", response_class=HTMLResponse)
async def weekly_review_page(
    request: Request,
    week_offset: int = Query(0, description="0 for current week, -1 for last week"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    """Display comprehensive weekly review with patterns and experiment."""
    
    review = await get_weekly_review(db=db, user_id=user.id, week_offset=week_offset)
    
    await track(user.id, "weekly_review_page_viewed", {"week_offset": week_offset}, db=db)
    
    return templates.TemplateResponse(
        "weekly_review.html",
        {
            "request": request,
            "user": user,
            "summary": review["summary"],
            "experiment": review["experiment"],
            "week_label": review["week_label"],
            "week_offset": week_offset,
        },
    )


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    """Display adaptive insights and recommendations."""
    
    recommendations = await get_adaptive_recommendations(db=db, user_id=user.id)
    
    await track(user.id, "insights_page_viewed", {}, db=db)
    
    return templates.TemplateResponse(
        "insights.html",
        {
            "request": request,
            "user": user,
            "recommendations": recommendations,
        },
    )

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.observability.analytics import track
from app.schemas.sprint import TodayHistoryResponse
from app.services.history import get_today_history

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/today", response_model=TodayHistoryResponse)
async def today(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TodayHistoryResponse:
    today = await get_today_history(db=db, user_id=current_user.id)
    await track(current_user.id, "history_viewed", {"date": today.date}, db=db)
    return today

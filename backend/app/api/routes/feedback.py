from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.feedback import FeedbackCreate
from app.services.feedback import FeedbackRateLimitError, create_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit(
    payload: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    try:
        fb = await create_feedback(
            db=db,
            user_id=current_user.id,
            message=payload.message,
            context=payload.context,
        )
    except FeedbackRateLimitError:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="feedback_rate_limited")

    return {"id": str(fb.id)}

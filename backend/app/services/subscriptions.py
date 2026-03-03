from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.subscription import Subscription


FREE = "FREE"
PRO = "PRO"


def _is_active(*, status: str | None, current_period_end: datetime | None) -> bool:
    if status not in {"active", "trialing"}:
        return False
    if current_period_end is None:
        return True
    return current_period_end > datetime.now(timezone.utc)


async def get_subscription(*, db: AsyncSession, user_id: UUID) -> Subscription | None:
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    return result.scalar_one_or_none()


async def get_effective_plan(*, db: AsyncSession, user_id: UUID) -> str:
    sub = await get_subscription(db=db, user_id=user_id)
    if sub is None:
        return FREE
    if sub.plan == PRO and _is_active(status=sub.status, current_period_end=sub.current_period_end):
        return PRO
    return FREE

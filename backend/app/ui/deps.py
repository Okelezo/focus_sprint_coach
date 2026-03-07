from datetime import datetime, timezone
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models.user import User
from app.db.session import get_db


UI_AUTH_COOKIE_NAME = "ui_access_token"


async def get_current_user_from_cookie(
    db: AsyncSession = Depends(get_db),
    token: str | None = Cookie(default=None, alias=UI_AUTH_COOKIE_NAME),
) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")

    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
        user_id = UUID(str(sub))
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")

    if user.is_guest and user.guest_expires_at is not None:
        now = datetime.now(timezone.utc)
        expires_at = user.guest_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now >= expires_at:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="guest_expired")

    return user

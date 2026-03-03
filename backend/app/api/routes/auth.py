from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.observability.analytics import track
from app.services.auth import AuthError, login_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserRead:
    try:
        user = await register_user(db=db, email=str(payload.email).lower(), password=payload.password)
        await track(user.id, "user_registered", {}, db=db)
        return UserRead.model_validate(user)
    except AuthError as e:
        if str(e) == "email_already_registered":
            raise HTTPException(status_code=400, detail="email_already_registered")
        raise


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        token = await login_user(db=db, email=str(payload.email).lower(), password=payload.password)
        # We only know the user_id inside login_user; for MVP we re-query here to avoid changing auth service signature.
        from sqlalchemy import select

        from app.db.models.user import User

        result = await db.execute(select(User).where(User.email == str(payload.email).lower()))
        user = result.scalar_one_or_none()
        if user is not None:
            await track(user.id, "user_logged_in", {}, db=db)
        return TokenResponse(access_token=token)
    except AuthError:
        raise HTTPException(status_code=401, detail="invalid_credentials")

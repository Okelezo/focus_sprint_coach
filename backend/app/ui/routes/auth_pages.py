from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.core.settings import get_settings
from app.db.models.user import User
from app.db.session import get_db
from app.observability.analytics import track
from app.services.auth import AuthError, login_user, register_user
from app.ui.deps import UI_AUTH_COOKIE_NAME
from app.ui.templates import templates

router = APIRouter(tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("privacy.html", {"request": request})


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("terms.html", {"request": request})


@router.post("/ui/guest")
async def ui_guest(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    email = f"guest-{uuid4()}@guest.local"
    password_hash = hash_password(str(uuid4()))
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    user = User(email=email, password_hash=password_hash, is_guest=True, guest_expires_at=expires_at)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await track(user.id, "guest_created", {"expires_at": expires_at.isoformat()}, db=db)
    await track(user.id, "user_logged_in", {"method": "guest"}, db=db)

    settings = get_settings()
    token = create_access_token(subject=str(user.id))

    if request.headers.get("HX-Request"):
        resp = JSONResponse(content="", status_code=200)
        resp.headers["HX-Redirect"] = "/app"
    else:
        resp = RedirectResponse(url="/app", status_code=303)

    resp.set_cookie(
        UI_AUTH_COOKIE_NAME,
        token,
        httponly=True,
        samesite=settings.ui_cookie_samesite,
        secure=settings.ui_cookie_secure_effective(),
        max_age=int(timedelta(minutes=settings.access_token_expire_minutes).total_seconds()),
        path="/",
    )
    return resp


@router.post("/ui/register")
async def ui_register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await register_user(db=db, email=email.lower(), password=password)
        await track(user.id, "user_registered", {}, db=db)
    except AuthError:
        return templates.TemplateResponse(
            "partials/auth_error.html",
            {"request": request, "message": "email_already_registered"},
            status_code=400,
        )

    token = await login_user(db=db, email=email.lower(), password=password)
    from sqlalchemy import select

    from app.db.models.user import User

    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        await track(user.id, "user_logged_in", {}, db=db)

    settings = get_settings()

    if request.headers.get("HX-Request"):
        resp = JSONResponse(content="", status_code=200)
        resp.headers["HX-Redirect"] = "/app"
    else:
        resp = RedirectResponse(url="/app", status_code=303)
    resp.set_cookie(
        UI_AUTH_COOKIE_NAME,
        token,
        httponly=True,
        samesite=settings.ui_cookie_samesite,
        secure=settings.ui_cookie_secure_effective(),
        max_age=int(timedelta(minutes=settings.access_token_expire_minutes).total_seconds()),
        path="/",
    )
    return resp


@router.post("/ui/login")
async def ui_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        token = await login_user(db=db, email=email.lower(), password=password)
    except AuthError:
        return templates.TemplateResponse(
            "partials/auth_error.html",
            {"request": request, "message": "invalid_credentials"},
            status_code=401,
        )

    from sqlalchemy import select

    from app.db.models.user import User

    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        await track(user.id, "user_logged_in", {}, db=db)

    settings = get_settings()

    if request.headers.get("HX-Request"):
        resp = JSONResponse(content="", status_code=200)
        resp.headers["HX-Redirect"] = "/app"
    else:
        resp = RedirectResponse(url="/app", status_code=303)
    resp.set_cookie(
        UI_AUTH_COOKIE_NAME,
        token,
        httponly=True,
        samesite=settings.ui_cookie_samesite,
        secure=settings.ui_cookie_secure_effective(),
        max_age=int(timedelta(minutes=settings.access_token_expire_minutes).total_seconds()),
        path="/",
    )
    return resp


@router.post("/ui/logout")
async def ui_logout() -> RedirectResponse:
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(UI_AUTH_COOKIE_NAME, path="/")
    return resp

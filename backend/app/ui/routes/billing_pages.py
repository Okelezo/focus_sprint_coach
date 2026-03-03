from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.db.session import get_db
from app.services.subscriptions import get_effective_plan
from app.ui.deps import get_current_user_from_cookie
from app.ui.templates import templates

router = APIRouter(prefix="/app", tags=["ui"])


@router.get("/billing", response_class=HTMLResponse)
async def billing_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> HTMLResponse:
    plan = await get_effective_plan(db=db, user_id=user.id)
    status = request.query_params.get("status")
    return templates.TemplateResponse(
        "billing.html",
        {"request": request, "user": user, "plan": plan, "status": status},
    )


@router.post("/billing/upgrade")
async def billing_upgrade(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> RedirectResponse:
    from app.api.routes.billing import create_checkout

    settings = get_settings()
    settings.app_base_url  # ensure settings loaded

    result = await create_checkout(db=db, current_user=user)
    return RedirectResponse(url=result["url"], status_code=303)


@router.post("/billing/manage")
async def billing_manage(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_from_cookie),
) -> RedirectResponse:
    from app.api.routes.billing import portal_session

    result = await portal_session(db=db, current_user=user)
    return RedirectResponse(url=result["url"], status_code=303)

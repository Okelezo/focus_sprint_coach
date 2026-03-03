from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.settings import get_settings
from app.db.models.subscription import Subscription
from app.db.models.user import User
from app.db.session import get_db
from app.services.stripe_client import construct_event, create_checkout_session, create_portal_session

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/create-checkout-session")
async def create_checkout(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    settings = get_settings()
    if not settings.stripe_price_pro:
        raise HTTPException(status_code=500, detail="missing_stripe_price_pro")

    result = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id))
    sub = result.scalar_one_or_none()

    success_url = settings.app_base_url.rstrip("/") + "/app/billing?status=success"
    cancel_url = settings.app_base_url.rstrip("/") + "/app/billing?status=cancel"

    session = create_checkout_session(
        customer_id=(sub.stripe_customer_id if sub else None),
        price_id=settings.stripe_price_pro,
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(current_user.id),
    )

    return {"url": session.url}


@router.post("/portal-session")
async def portal_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    settings = get_settings()

    result = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id))
    sub = result.scalar_one_or_none()
    if sub is None or not sub.stripe_customer_id:
        raise HTTPException(status_code=400, detail="no_stripe_customer")

    return_url = settings.app_base_url.rstrip("/") + "/app/billing"
    session = create_portal_session(customer_id=sub.stripe_customer_id, return_url=return_url)
    return {"url": session.url}


@router.post("/webhook")
async def webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=500, detail="missing_stripe_webhook_secret")

    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not sig:
        raise HTTPException(status_code=400, detail="missing_signature")

    try:
        event = construct_event(payload=payload, sig_header=sig, secret=settings.stripe_webhook_secret)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_signature")

    etype = event.get("type")
    data_obj = (event.get("data") or {}).get("object") or {}

    if etype == "checkout.session.completed":
        customer_id = data_obj.get("customer")
        subscription_id = data_obj.get("subscription")
        client_ref = data_obj.get("client_reference_id")
        if customer_id and subscription_id and client_ref:
            from uuid import UUID

            user_id = UUID(str(client_ref))
            result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
            sub = result.scalar_one_or_none()
            if sub is None:
                sub = Subscription(user_id=user_id)
                db.add(sub)
            sub.stripe_customer_id = str(customer_id)
            sub.stripe_subscription_id = str(subscription_id)
            sub.plan = "PRO"
            sub.status = "active"
            await db.commit()

    if etype in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        customer_id = data_obj.get("customer")
        subscription_id = data_obj.get("id")
        status_val = data_obj.get("status")
        cpe = data_obj.get("current_period_end")

        if customer_id and subscription_id:
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == str(subscription_id))
            )
            sub = result.scalar_one_or_none()
            if sub is not None:
                sub.status = str(status_val) if status_val is not None else sub.status
                sub.plan = "PRO" if sub.status in {"active", "trialing"} else "FREE"
                sub.stripe_customer_id = str(customer_id)
                if cpe is not None:
                    sub.current_period_end = datetime.fromtimestamp(int(cpe), tz=timezone.utc)
                await db.commit()

    return {"ok": True}

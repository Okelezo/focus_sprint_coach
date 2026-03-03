from __future__ import annotations

from typing import Any

from app.core.settings import get_settings


def _stripe():
    import stripe

    settings = get_settings()
    if not settings.stripe_secret_key:
        raise RuntimeError("missing_stripe_secret_key")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def create_checkout_session(
    *,
    customer_id: str | None,
    price_id: str,
    success_url: str,
    cancel_url: str,
    client_reference_id: str,
) -> Any:
    stripe = _stripe()
    return stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=client_reference_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
    )


def create_portal_session(*, customer_id: str, return_url: str) -> Any:
    stripe = _stripe()
    return stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)


def construct_event(*, payload: bytes, sig_header: str, secret: str) -> Any:
    import stripe

    return stripe.Webhook.construct_event(payload, sig_header, secret)

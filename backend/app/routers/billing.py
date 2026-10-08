import logging
from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_service_provider_profile, require_approved_service_provider
from app.models.service_provider import ServiceProviderProfile
from app.models.enums import SubscriptionStatus
from app.models.user import User
from app.services.stripe_service import map_stripe_status

router = APIRouter(tags=["billing"])
settings = get_settings()
logger = logging.getLogger("billing")


@router.post("/billing/checkout-session")
def create_checkout_session(
    plan: str = "monthly", user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)
):
    price_id = settings.stripe_price_id_annual if plan == "annual" else settings.stripe_price_id_monthly
    if not price_id:
        raise HTTPException(status_code=400, detail="Billing isn't configured yet — a Stripe price ID is missing.")

    cp = get_service_provider_profile(user, db)

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        # Reuse the existing Stripe customer if this service provider has billed
        # before (e.g. resubscribing after a cancellation) instead of
        # creating a duplicate customer record.
        customer=cp.stripe_customer_id or None,
        customer_email=None if cp.stripe_customer_id else user.email,
        client_reference_id=user.id,
        # The webhook has no session/user context of its own — metadata is
        # how it knows which service_provider_profiles row to update.
        metadata={"service_provider_id": user.id},
        subscription_data={"metadata": {"service_provider_id": user.id}},
        success_url=f"{settings.app_url}/service-provider/feed?subscribed=1",
        cancel_url=f"{settings.app_url}/service-provider/subscribe",
    )
    if not session.url:
        raise HTTPException(status_code=502, detail="Could not start checkout. Try again.")
    return {"url": session.url}


@router.post("/billing/portal-session")
def create_billing_portal_session(user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    cp = get_service_provider_profile(user, db)
    if not cp.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account yet — subscribe first.")

    session = stripe.billing_portal.Session.create(
        customer=cp.stripe_customer_id, return_url=f"{settings.app_url}/service-provider/subscribe"
    )
    return {"url": session.url}


# Webhooks arrive with no user session — authenticated by the signature
# check below, not by auth cookies.
@router.post("/billing/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("stripe-signature")

    if not signature or not settings.stripe_webhook_secret:
        raise HTTPException(status_code=400, detail="Missing signature or webhook secret")

    try:
        event = stripe.Webhook.construct_event(body, signature, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            service_provider_id = (data.get("metadata") or {}).get("service_provider_id") or data.get("client_reference_id")
            if service_provider_id and data.get("subscription") and data.get("customer"):
                subscription = stripe.Subscription.retrieve(data["subscription"])
                cp = db.get(ServiceProviderProfile, service_provider_id)
                if cp:
                    had_access = cp.is_verified_active
                    cp.stripe_customer_id = data["customer"]
                    cp.stripe_subscription_id = subscription.id
                    cp.subscription_status = SubscriptionStatus(map_stripe_status(subscription.status))
                    cp.subscription_current_period_end = datetime.utcfromtimestamp(subscription.current_period_end)
                    db.commit()
                    _tell_access_change(db, cp, had_access)

        # Covers plan changes, renewals, payment failures, and
        # cancellations — Stripe sends this on essentially every status
        # change after the initial checkout, so it's the source of truth
        # going forward.
        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            service_provider_id = (data.get("metadata") or {}).get("service_provider_id")
            cp = None
            if service_provider_id:
                cp = db.get(ServiceProviderProfile, service_provider_id)
            else:
                cp = (
                    db.query(ServiceProviderProfile)
                    .filter(ServiceProviderProfile.stripe_subscription_id == data["id"])
                    .first()
                )
            if cp:
                had_access = cp.is_verified_active
                cp.subscription_status = SubscriptionStatus(map_stripe_status(data["status"]))
                cp.subscription_current_period_end = datetime.utcfromtimestamp(data["current_period_end"])
                db.commit()
                _tell_access_change(db, cp, had_access)
        # Unhandled event types are expected — Stripe sends many more than
        # we act on. No-op is correct here.
    except Exception:
        # Return 500 so Stripe retries — better a duplicate delivery than a
        # silently missed subscription state change. Logged server-side
        # only; the response never echoes exception internals back out.
        logger.exception("failed to process stripe webhook event %s", event_type)
        raise HTTPException(status_code=500, detail="Internal error processing webhook")

    return {"received": True}


def _tell_access_change(db: Session, cp: ServiceProviderProfile, had_access: bool) -> None:
    """Stage 9.5: after the subscription state is committed (Stripe is the
    authority), tell everyone acting for the provider when that opened or
    closed its marketplace access (is_verified_active -- so a provider whose
    access rests on an admin override isn't told it lost access it still
    has). Only on an actual change, so Stripe's retries and renewals don't
    repeat it. Best-effort: never fails the webhook."""
    from app.models.enums import NotificationType
    from app.models.user import User
    from app.services.notify import notify_team

    if cp.is_verified_active == had_access:
        return
    try:
        notify_team(db, db.get(User, cp.user_id), NotificationType.payment_activated if cp.is_verified_active else NotificationType.payment_failed,
                    link="/service-provider/subscribe", organization_id=cp.organization_id)
    except Exception:  # noqa: BLE001 -- the subscription state is already recorded
        db.rollback()
        logger.exception("could not notify %s of a subscription change", cp.user_id)

import logging
from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_contractor_profile, require_approved_contractor
from app.models.contractor import ContractorProfile
from app.models.enums import SubscriptionStatus
from app.models.user import User
from app.services.stripe_service import map_stripe_status

router = APIRouter(tags=["billing"])
settings = get_settings()
logger = logging.getLogger("billing")


@router.post("/billing/checkout-session")
def create_checkout_session(
    plan: str = "monthly", user: User = Depends(require_approved_contractor), db: Session = Depends(get_db)
):
    price_id = settings.stripe_price_id_annual if plan == "annual" else settings.stripe_price_id_monthly
    if not price_id:
        raise HTTPException(status_code=400, detail="Billing isn't configured yet — a Stripe price ID is missing.")

    cp = get_contractor_profile(user, db)

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        # Reuse the existing Stripe customer if this contractor has billed
        # before (e.g. resubscribing after a cancellation) instead of
        # creating a duplicate customer record.
        customer=cp.stripe_customer_id or None,
        customer_email=None if cp.stripe_customer_id else user.email,
        client_reference_id=user.id,
        # The webhook has no session/user context of its own — metadata is
        # how it knows which contractor_profiles row to update.
        metadata={"contractor_id": user.id},
        subscription_data={"metadata": {"contractor_id": user.id}},
        success_url=f"{settings.app_url}/contractor/feed?subscribed=1",
        cancel_url=f"{settings.app_url}/contractor/subscribe",
    )
    if not session.url:
        raise HTTPException(status_code=502, detail="Could not start checkout. Try again.")
    return {"url": session.url}


@router.post("/billing/portal-session")
def create_billing_portal_session(user: User = Depends(require_approved_contractor), db: Session = Depends(get_db)):
    cp = get_contractor_profile(user, db)
    if not cp.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account yet — subscribe first.")

    session = stripe.billing_portal.Session.create(
        customer=cp.stripe_customer_id, return_url=f"{settings.app_url}/contractor/subscribe"
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
            contractor_id = (data.get("metadata") or {}).get("contractor_id") or data.get("client_reference_id")
            if contractor_id and data.get("subscription") and data.get("customer"):
                subscription = stripe.Subscription.retrieve(data["subscription"])
                cp = db.get(ContractorProfile, contractor_id)
                if cp:
                    cp.stripe_customer_id = data["customer"]
                    cp.stripe_subscription_id = subscription.id
                    cp.subscription_status = SubscriptionStatus(map_stripe_status(subscription.status))
                    cp.subscription_current_period_end = datetime.utcfromtimestamp(subscription.current_period_end)
                    db.commit()

        # Covers plan changes, renewals, payment failures, and
        # cancellations — Stripe sends this on essentially every status
        # change after the initial checkout, so it's the source of truth
        # going forward.
        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            contractor_id = (data.get("metadata") or {}).get("contractor_id")
            cp = None
            if contractor_id:
                cp = db.get(ContractorProfile, contractor_id)
            else:
                cp = (
                    db.query(ContractorProfile)
                    .filter(ContractorProfile.stripe_subscription_id == data["id"])
                    .first()
                )
            if cp:
                cp.subscription_status = SubscriptionStatus(map_stripe_status(data["status"]))
                cp.subscription_current_period_end = datetime.utcfromtimestamp(data["current_period_end"])
                db.commit()
        # Unhandled event types are expected — Stripe sends many more than
        # we act on. No-op is correct here.
    except Exception:
        # Return 500 so Stripe retries — better a duplicate delivery than a
        # silently missed subscription state change. Logged server-side
        # only; the response never echoes exception internals back out.
        logger.exception("failed to process stripe webhook event %s", event_type)
        raise HTTPException(status_code=500, detail="Internal error processing webhook")

    return {"received": True}

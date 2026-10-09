"""Stage 9.13: Kuwait pilot readiness -- the small fixes the launch audit
needed. A provider whose payment failed is sent to fix it, not into a second
subscription; the support contact customers are told to use is something an
admin can set (and is empty, never invented, until then)."""
import stripe

from app.config import get_settings
from app.models.enums import SubscriptionStatus
from app.models.service_provider import ServiceProviderProfile
from tests.test_stage4_9_participation import _account
from tests.test_stage8_15_review_moderation import _admin


def test_a_live_subscription_is_never_started_twice(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_price_id_monthly", "price_m")
    started = []
    monkeypatch.setattr(stripe.checkout.Session, "create",
                        lambda **kw: (started.append(kw), type("S", (), {"url": "https://stripe.test/c"})())[1])
    provider = _account(db, "service_provider", "kw-provider@example.com", paid=False)
    cp = db.get(ServiceProviderProfile, provider.get("/auth/me").json()["id"])

    # Never subscribed, or cancelled: checkout opens.
    assert provider.post("/billing/checkout-session").status_code == 200
    for status in (SubscriptionStatus.active, SubscriptionStatus.trialing, SubscriptionStatus.past_due):
        cp.subscription_status, cp.stripe_customer_id = status, "cus_1"
        db.commit()
        r = provider.post("/billing/checkout-session")
        assert r.status_code == 409 and "Manage billing" in r.json()["detail"]
    assert len(started) == 1
    # In Arabic too.
    r = provider.post("/billing/checkout-session", headers={"Accept-Language": "ar"})
    assert "إدارة الفوترة" in r.json()["detail"]

    cp.subscription_status = SubscriptionStatus.canceled
    db.commit()
    assert provider.post("/billing/checkout-session").status_code == 200 and len(started) == 2


def test_support_contact_is_set_by_an_admin(db):
    admin = _admin(db)
    assert admin.get("/public/cms?language=en").json()["support_contact"] == ""
    assert admin.put("/admin/cms/support_contact/en", json={"value": "support@example.com"}).status_code in (200, 201)
    assert admin.get("/public/cms?language=en").json()["support_contact"] == "support@example.com"

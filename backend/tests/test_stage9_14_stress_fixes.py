"""Stage 9.14: what the end-to-end production stress test found. An
Arabic visitor's account is Arabic from sign-up (pages and notifications),
and checkout when Stripe can't be reached says so plainly -- a clean 502,
nothing started -- instead of an unhandled 500."""
import stripe
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models.service_provider import ServiceProviderProfile
from tests.test_stage4_9_participation import _account


def test_sign_up_keeps_the_visitors_language(db):
    c = TestClient(app)
    me = c.post("/auth/signup", json={"email": "hamad@example.com", "password": "password123", "full_name": "Hamad",
                                      "role": "service_provider", "language": "ar"}).json()
    assert me["language"] == "ar"
    assert c.get("/auth/me").json()["language"] == "ar"
    # Without one, English as before.
    other = TestClient(app).post("/auth/signup", json={"email": "sara@example.com", "password": "password123", "full_name": "Sara", "role": "owner"}).json()
    assert other["language"] == "en"


def test_checkout_when_stripe_fails_is_a_clean_error(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_price_id_monthly", "price_m")

    def unreachable(**kw):
        raise stripe.error.APIConnectionError("Network error")

    monkeypatch.setattr(stripe.checkout.Session, "create", unreachable)
    provider = _account(db, "service_provider", "kw-checkout@example.com", paid=False)
    r = provider.post("/billing/checkout-session")
    assert r.status_code == 502 and r.json()["detail"] == "Could not start checkout. Try again."
    assert provider.post("/billing/checkout-session", headers={"Accept-Language": "ar"}).json()["detail"] == "تعذّر بدء عملية الدفع. حاول مرة أخرى."
    cp = db.get(ServiceProviderProfile, provider.get("/auth/me").json()["id"])
    db.refresh(cp)
    assert cp.stripe_customer_id is None and (cp.subscription_status is None or cp.subscription_status.value == "not_started")

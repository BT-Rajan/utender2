"""Stage 9.6: Stripe drives one authoritative subscription state on the
billed stakeholder -- the organisation, never the member who clicked --
through signed webhooks only. Repeats change nothing, older events can't roll
it back, failure and recovery move access accordingly, cancellation is
shown before it bites, and none of it touches marketplace history."""
import hashlib
import hmac
import json
import time

import stripe
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models.agreement import Agreement
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import NotificationType as N
from app.models.notification import Notification
from app.models.service_provider import ServiceProviderProfile
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _tender
from tests.test_stage8_7_provider_reputation import _award
from tests.test_stage8_15_review_moderation import _admin

SECRET = "whsec_test"


def _sub(status, *, sub_id="sub_1", cancel=False, interval="month"):
    return {"id": sub_id, "object": "subscription", "status": status, "current_period_end": int(time.time()) + 30 * 86400,
            "cancel_at_period_end": cancel, "metadata": {}, "items": {"data": [{"price": {"recurring": {"interval": interval}}}]}}


def _post(event):
    payload = json.dumps(event)
    t = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{t}.{payload}".encode(), hashlib.sha256).hexdigest()
    return TestClient(app).post("/billing/webhook", content=payload, headers={"stripe-signature": f"t={t},v1={sig}", "content-type": "application/json"})


def _event(kind, obj, created, eid):
    return {"id": eid, "object": "event", "type": kind, "created": created, "data": {"object": obj}}


def test_billing_follows_stripe_onto_the_organisation(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", SECRET)
    monkeypatch.setattr(get_settings(), "stripe_price_id_monthly", "price_m")
    admin = _admin(db)
    owner, _, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, x_id, sami_id = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    other = _account(db, "service_provider", "y@example.com")
    cp = db.get(ServiceProviderProfile, x_id)
    cp.payment_override_active = False  # access rests on the subscription alone
    db.commit()

    # A. A member subscribes: Stripe is told the organisation's profile, not the member.
    created = {}
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kw: (created.update(kw), type("S", (), {"url": "https://stripe.test/c"})())[1])
    assert sami.post("/billing/checkout-session").json()["url"] == "https://stripe.test/c"
    assert created["client_reference_id"] == x_id and created["metadata"]["service_provider_id"] == x_id
    monkeypatch.setattr(stripe.Subscription, "retrieve", lambda sid: _sub("active"))
    t0 = int(time.time())
    done = _event("checkout.session.completed", {"object": "checkout.session", "subscription": "sub_1", "customer": "cus_1",
                                                  "client_reference_id": x_id, "metadata": {"service_provider_id": x_id}}, t0, "evt_1")
    # B. Delivered twice: one state, one audit entry, one notice.
    assert _post(done).status_code == 200 and _post(done).status_code == 200
    db.expire_all()
    cp = db.get(ServiceProviderProfile, x_id)
    assert (cp.subscription_status.value, cp.subscription_interval, cp.stripe_customer_id, cp.is_verified_active) == ("active", "month", "cus_1", True)
    assert db.get(ServiceProviderProfile, sami_id).stripe_subscription_id is None  # the member's own row is untouched
    assert db.query(AuditLog).filter(AuditLog.action == "billing.subscription_status", AuditLog.target_id == x_id).count() == 1
    n = lambda kind: db.query(Notification).filter(Notification.user_id == x_id, Notification.type == kind).count()  # noqa: E731
    assert n(N.payment_activated) == 1

    # Work won while subscribed.
    pid = _tender(owner, title="Tower maintenance")
    _award(owner, amal, pid)

    # C. Payment fails: access goes, on the server, whatever the page shows (F).
    assert _post(_event("customer.subscription.updated", _sub("past_due"), t0 + 10, "evt_2")).status_code == 200
    db.expire_all()
    assert db.get(ServiceProviderProfile, x_id).subscription_status.value == "past_due"
    assert amal.post(f"/projects/{_tender(owner, title='Next')}/offers", json={"amount": "100"}).status_code == 403
    assert n(N.payment_failed) == 1
    # H. An older event arriving late is ignored -- it can't roll the state back.
    assert _post(_event("customer.subscription.updated", _sub("active"), t0 + 5, "evt_old")).status_code == 200
    db.expire_all()
    assert db.get(ServiceProviderProfile, x_id).subscription_status.value == "past_due"
    # D. Recovered.
    assert _post(_event("customer.subscription.updated", _sub("active"), t0 + 20, "evt_3")).status_code == 200
    db.expire_all()
    assert db.get(ServiceProviderProfile, x_id).is_verified_active is True
    # Told again -- as one refreshed unread notice, not a second copy (9.5 de-duplication).
    latest = db.query(Notification).filter(Notification.user_id == x_id).order_by(Notification.created_at.desc()).first()
    assert n(N.payment_activated) == 1 and latest.type == N.payment_activated

    # E. Cancellation: scheduled (still active, shown), then ended -- access goes, history stays.
    _post(_event("customer.subscription.updated", _sub("active", cancel=True), t0 + 30, "evt_4"))
    detail = admin.get(f"/admin/service-providers/{x_id}").json()["service_provider"]
    assert (detail["subscription_status"], detail["subscription_cancel_at_period_end"], detail["subscription_interval"]) == ("active", True, "month")
    assert detail["subscription_event_at"]
    _post(_event("customer.subscription.deleted", _sub("canceled"), t0 + 40, "evt_5"))
    db.expire_all()
    assert db.get(ServiceProviderProfile, x_id).is_verified_active is False
    assert db.query(AwardRecord).filter(AwardRecord.project_id == pid).one().service_provider_id == x_id
    assert db.query(Agreement).filter(Agreement.project_id == pid).count() == 1
    assert amal.get(f"/projects/{pid}/agreement").status_code == 200  # its won work stays reachable

    # A subscription an older checkout put on a member's own row moves to the organisation.
    member_row = db.get(ServiceProviderProfile, sami_id)
    member_row.stripe_subscription_id, member_row.stripe_customer_id = "sub_old", "cus_old"
    db.commit()
    _post(_event("customer.subscription.updated", _sub("active", sub_id="sub_old"), t0 + 50, "evt_6"))
    db.expire_all()
    assert db.get(ServiceProviderProfile, x_id).stripe_subscription_id == "sub_old"
    assert db.get(ServiceProviderProfile, sami_id).stripe_subscription_id is None

    # Webhooks must be signed; nobody reaches another stakeholder's billing; owners aren't billed.
    assert TestClient(app).post("/billing/webhook", content=json.dumps(done)).status_code == 400
    assert TestClient(app).post("/billing/webhook", content=json.dumps(done), headers={"stripe-signature": "t=1,v1=bad"}).status_code == 400
    assert other.post("/billing/portal-session").status_code in (400, 403)  # its own (none yet) -- never X's
    assert owner.post("/billing/checkout-session").status_code == 403
    assert "cus_1" not in amal.get("/service-provider/profile").text  # no Stripe ids handed to the browser

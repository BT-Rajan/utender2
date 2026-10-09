"""Stage 9.9: the operator's numbers come from the authoritative records --
a requirement counts once however often it is amended, an offer once however
often it is revised, an award is not a completion, a cancelled requirement is
not active, periods are UTC from the server clock, subscriptions are Stripe's
state -- and only admins see them, with no prices or names."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import SubscriptionStatus
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from tests.stage7_helpers import complete_transaction
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_15_review_moderation import _admin


def _m(admin, period="30d"):
    body = admin.get("/admin/metrics", params={"period": period}).json()
    assert all(body[s]["available"] for s in ("activity", "requirement_funnel", "provider_funnel", "subscriptions"))
    return body


def test_metrics_follow_the_records(db):
    admin = _admin(db)
    owner = _account(db, "owner", "owner@example.com")
    providers = [_account(db, "service_provider", f"p{i}@example.com") for i in range(3)]
    m = _m(admin)
    assert m["activity"]["data"]["requirements_published"] == 0 and m["definitions"]["transactions_completed"]
    assert m["provider_funnel"]["data"]["registered"] == 3 and m["provider_funnel"]["data"]["submitted_an_offer"] == 0

    # A/B. Published, no offers; an amendment is not a second requirement.
    pid = _tender(owner, title="Tower maintenance")
    assert owner.patch(f"/projects/{pid}", json={"description": "Two towers."}).status_code == 200
    f = _m(admin)["requirement_funnel"]["data"]
    assert (f["published"], f["received_offers"]) == (1, 0)

    # C. Three offers; one is revised (still one offer); no prices in the response.
    for p in providers:
        _submitted(p, pid)
    assert providers[0].post(f"/projects/{pid}/offers/draft/submit").status_code == 409  # H. a retry is refused
    m = _m(admin)
    assert m["activity"]["data"]["offers_submitted"] == 3 and m["requirement_funnel"]["data"]["received_offers"] == 1
    assert m["provider_funnel"]["data"]["submitted_an_offer"] == 3
    assert "1000" not in admin.get("/admin/metrics").text and "p0@" not in admin.get("/admin/metrics").text

    # D/E. Awarded: an award, not a completion; completed: one completion, still one award.
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner.get("/owner/projects")
    win = providers[0].get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{win}/approve", json={"acknowledge_earlier_version": True}).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/offers/{win}/approve", json={"acknowledge_earlier_version": True}).status_code >= 400  # H
    a = _m(admin)["activity"]["data"]
    assert (a["awards"], a["transactions_completed"]) == (1, 0)
    complete_transaction(owner, providers[0], pid)
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 4}).status_code == 200
    m = _m(admin)
    assert (m["activity"]["data"]["awards"], m["activity"]["data"]["transactions_completed"], m["activity"]["data"]["reviews"]) == (1, 1, 1)
    assert (m["requirement_funnel"]["data"]["awarded"], m["requirement_funnel"]["data"]["completed"]) == (1, 1)

    # F. A cancelled requirement ends without an award and is never active.
    c = _tender(owner, title="Cancelled")
    owner.post(f"/owner/projects/{c}/cancel", json={"reason": "other"})
    f = _m(admin)["requirement_funnel"]["data"]
    assert (f["published"], f["ended_without_award"]) == (2, 1)
    assert admin.get("/admin/overview").json()["requirements"]["data"]["by_status"]["open"] == 0

    # G. Subscriptions: Stripe's state, not the override.
    for p, status in zip(providers, (SubscriptionStatus.active, SubscriptionStatus.past_due, None)):
        cp = db.get(ServiceProviderProfile, p.get("/auth/me").json()["id"])
        cp.subscription_status, cp.payment_override_active = status, status is None
    db.commit()
    s = _m(admin)["subscriptions"]["data"]
    assert (s["paying"], s["past_due"], s["override_only"]) == (1, 1, 1)

    # Periods: everything here happened today; an account made before the period counts as returning.
    assert _m(admin, "today")["activity"]["data"]["requirements_published"] == 2
    db.get(User, owner.get("/auth/me").json()["id"]).created_at = datetime.utcnow() - timedelta(days=40)
    db.commit()
    a = _m(admin, "30d")["activity"]["data"]
    assert a["returning_people"] >= 1 and a["active_people"] >= a["returning_people"]
    assert _m(admin, "all")["activity"]["data"]["returning_people"] is None  # no "before" for all time
    assert admin.get("/admin/metrics", params={"period": "forever"}).status_code == 422

    # Admin only.
    for client in (owner, providers[0]):
        assert client.get("/admin/metrics").status_code == 403
    assert TestClient(app).get("/admin/metrics").status_code == 401

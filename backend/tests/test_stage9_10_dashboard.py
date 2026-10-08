"""Stage 9.10: the admin dashboard (the overview) answers "what needs me
now?" -- verification waiting (named, linked to the review), requirements
without offers, transactions waiting on a party (deliverables, changes),
billing problems, emails that failed, reports to decide -- each linked to its
existing admin page, kept apart from state counts, never claiming health it
can't prove, and showing no prices; admins only."""
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement, Milestone, Variation
from app.models.email_failure import EmailFailure
from app.models.enums import SubscriptionStatus, VerificationStatus
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _tender
from tests.test_stage8_7_provider_reputation import _award
from tests.test_stage8_15_review_moderation import _admin


def _attention(admin):
    body = admin.get("/admin/overview").json()
    assert body["attention"]["available"]
    return {a["kind"]: a for a in body["attention"]["data"]}


def test_the_dashboard_points_at_what_needs_attention(db):
    admin = _admin(db)
    owner = _account(db, "owner", "owner@example.com")
    x = _account(db, "service_provider", "x@example.com")
    x_id = x.get("/auth/me").json()["id"]
    waiting = _account(db, "service_provider", "waiting@example.com")
    w_id = waiting.get("/auth/me").json()["id"]

    # A. Morning check on a quiet platform: information, nothing to attend to, no false "healthy".
    body = admin.get("/admin/overview").json()
    assert body["attention"]["data"] == []
    bg = body["background"]["data"]
    assert bg["billing_webhook"] == "not_configured" and bg["email_delivery"] == "not_configured"
    assert "healthy" not in str(bg).lower()

    # B. A verification waiting -- named, and linked to its existing admin page.
    p = db.get(ServiceProviderProfile, w_id)
    p.verification_status, p.verification_submitted_at, p.company_name = VerificationStatus.pending_review, datetime.utcnow(), "Waiting Co"
    db.commit()
    item = _attention(admin)["providers_awaiting_review"]
    assert item["link"] == "/admin/service-providers/" and [(i["id"], i["title"]) for i in item["items"]] == [(w_id, "Waiting Co")]
    assert admin.get(f"{item['link']}{w_id}").status_code == 200

    # C. A requirement with no offers -- linked to its admin page.
    lonely = _tender(owner, title="No takers")
    item = _attention(admin)["open_without_offers"]
    assert lonely in [i["id"] for i in item["items"]] and admin.get(f"/admin/projects/{lonely}").status_code == 200

    # D/E. A transaction waiting on a party: a deliverable to review and a change to answer.
    pid = _tender(owner, title="Tower maintenance")
    _award(owner, x, pid)
    agreement = db.query(Agreement).filter(Agreement.project_id == pid).one()
    agreement.status = "active"
    db.add(Milestone(agreement_id=agreement.id, position=1, title="Phase 1", status="delivered", delivered_at=datetime.utcnow()))
    db.add(Variation(agreement_id=agreement.id, number=1, status="proposed", description="Extra floor", proposed_party="provider", proposed_at=datetime.utcnow()))
    db.commit()
    att = _attention(admin)
    for kind in ("deliverables_awaiting_owner", "changes_awaiting_answer"):
        assert [i["id"] for i in att[kind]["items"]] == [pid] and att[kind]["link"] == "/admin/projects/"
    assert admin.get(f"/admin/projects/{pid}").json()["transaction"]["status"] == "active"

    # F. Billing: a verified provider whose payment failed, named and linked; Stripe's last event shown, not "healthy".
    cp = db.get(ServiceProviderProfile, x_id)
    cp.payment_override_active, cp.subscription_status, cp.subscription_event_at = False, SubscriptionStatus.past_due, datetime.utcnow()
    db.commit()
    item = _attention(admin)["provider_payment_failed"]
    assert [i["id"] for i in item["items"]] == [x_id] and item["link"] == "/admin/service-providers/"
    assert admin.get("/admin/overview").json()["background"]["data"]["last_billing_event_at"]

    # G. A failed email: what and when, kept apart from the business action (no recipient shown).
    db.add(EmailFailure(recipient="someone@example.com", subject="Your offer was approved — Tower maintenance", error="RuntimeError: down"))
    db.commit()
    item = _attention(admin)["email_failures"]
    assert item["link"] == "" and item["items"][0]["title"].startswith("Your offer was approved")
    assert "someone@example.com" not in admin.get("/admin/overview").text

    # H. A reported review, linked to moderation.
    cp.payment_override_active = True
    db.commit()
    p2 = _tender(owner, title="Reviewed job")
    _award(owner, x, p2)
    complete_transaction(owner, x, p2)
    assert owner.post("/owner/reviews", json={"project_id": p2, "rating": 1}).status_code == 200
    assert x.post(f"/service-provider/projects/{p2}/review-reports", json={"target": "review", "reason": "abusive"}).status_code == 201
    assert _attention(admin)["open_review_reports"]["link"] == "/admin/review-reports"

    # No prices anywhere on the dashboard (the awarded offers were priced at 1000).
    assert "1000" not in admin.get("/admin/overview").text

    # I. Admins only.
    for c in (owner, x):
        assert c.get("/admin/overview").status_code == 403
        assert c.get("/admin/metrics").status_code == 403
    assert TestClient(app).get("/admin/overview").status_code == 401

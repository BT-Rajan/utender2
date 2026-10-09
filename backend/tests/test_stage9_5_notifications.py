"""Stage 9.5: important events reach the right people -- the current, active
members of the right organisation -- after the business state is committed,
without leaking sealed details, without uncontrolled duplicates, and without
a failed email changing anything but a recorded failure the operator sees.
Billing changes that open or close marketplace access are now told."""
import sys
import types

from app.config import get_settings
from app.models.email_failure import EmailFailure
from app.models.enums import NotificationType as N, SubscriptionStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.service_provider import ServiceProviderProfile
from app.routers.billing import _tell_access_change
from app.services import email as email_service
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_15_review_moderation import _admin


def _got(db, client_or_id, kind):
    uid = client_or_id if isinstance(client_or_id, str) else client_or_id.get("/auth/me").json()["id"]
    return db.query(Notification).filter(Notification.user_id == uid, Notification.type == kind).all()


def test_events_reach_the_right_people_and_failures_change_nothing(db, monkeypatch):
    admin = _admin(db)
    owner, noura, owner_id, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, x_id, sami_id = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    b = _account(db, "service_provider", "b@example.com")
    outsider = _account(db, "service_provider", "outsider@example.com")
    sent = []

    # J (set up): email is "configured" and every send fails.
    monkeypatch.setattr(get_settings(), "resend_api_key", "test-key")
    fake = types.SimpleNamespace(api_key=None, Emails=types.SimpleNamespace(send=lambda msg: (sent.append(msg), (_ for _ in ()).throw(RuntimeError("provider down")))[1]))
    monkeypatch.setitem(sys.modules, "resend", fake)

    # Noura is deactivated (9.2): from here she is told nothing, in-app or by email.
    admin.post(f"/admin/users/{noura_id}/deactivate")

    # A/B. Sealed tender: offers reach the owner side without names or amounts -- and the failing
    # email changes nothing: the offer stands, and the failure is recorded for the operator.
    pid = _tender(owner, title="Tower maintenance", sealed=True)
    _submitted(sami, pid)
    _submitted(b, pid)
    assert db.query(Offer).filter(Offer.project_id == pid, Offer.status == "submitted").count() == 2
    offer_notes = _got(db, owner, N.bid_submitted)
    assert len(offer_notes) == 1  # I. two offers, one unread notice for the same place -- not a pile
    assert "X Contracting" not in offer_notes[0].body and "A service provider" in offer_notes[0].body
    assert _got(db, noura_id, N.bid_submitted) == []
    assert not any("X Contracting" in m["html"] or "fahad" not in m["to"] and "noura" in m["to"] for m in sent)
    assert not any(m["to"] == "noura@gulf.example" for m in sent)
    assert db.query(EmailFailure).count() == len(sent) >= 1
    assert admin.get("/admin/overview").json()["background"]["data"]["email_delivery"] == "failing"

    # D. A material amendment reaches the bidders' sides.
    assert owner.patch(f"/projects/{pid}", json={"description": "Two towers."}).status_code == 200
    assert _got(db, amal, N.tender_amendment) and _got(db, sami, N.tender_amendment) and _got(db, b, N.tender_amendment)
    assert _got(db, outsider, N.tender_amendment) == []

    # C. Award: the winner's whole side is told it won, the other bidder that it didn't, an outsider nothing.
    from datetime import datetime, timedelta

    from app.models.project import Project

    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner.get("/owner/projects")
    win = sami.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{win}/approve", json={"acknowledge_earlier_version": True}).status_code == 200
    assert _got(db, amal, N.award_won) and _got(db, sami, N.award_won)
    assert _got(db, b, N.award_lost) and not _got(db, b, N.award_won)
    assert not _got(db, outsider, N.award_won) and not _got(db, outsider, N.award_lost)

    # E/F. Completion and review reach the other side.
    complete_transaction(owner, amal, pid)
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 4}).status_code == 200
    assert _got(db, amal, N.review_received) and _got(db, sami, N.review_received)

    # H. A member who leaves keeps their old notices, but their links open nothing any more.
    old = _got(db, sami, N.award_won)[0]
    assert amal.delete(f"/account/organization/members/{sami_id}").status_code == 200
    assert sami.get("/notifications").status_code == 200 and old.id in {n["id"] for n in sami.get("/notifications").json()}
    assert sami.get(f"/projects/{pid}/agreement").status_code in (403, 404)
    # ...and gets nothing new about the organisation.
    assert sami.post(f"/service-provider/projects/{pid}/review/received/response", json={"response": "x"}).status_code in (403, 404)
    assert amal.post(f"/service-provider/projects/{pid}/review/received/response", json={"response": "Thanks."}).status_code == 200
    assert _got(db, owner, N.review_response) and not _got(db, sami, N.review_response)

    # G. Billing: losing and regaining access is told once per change -- a webhook retry repeats nothing.
    cp = db.get(ServiceProviderProfile, x_id)
    # Access resting on an admin override isn't changed by billing -- so nothing is said.
    cp.payment_override_active, cp.subscription_status = True, SubscriptionStatus.active
    db.commit()
    had = cp.is_verified_active
    cp.subscription_status = SubscriptionStatus.past_due
    db.commit()
    _tell_access_change(db, cp, had)
    assert not _got(db, amal, N.payment_failed)
    cp.payment_override_active, cp.subscription_status = False, SubscriptionStatus.active
    db.commit()
    for status in (SubscriptionStatus.past_due, SubscriptionStatus.past_due, SubscriptionStatus.active):  # the repeat is a webhook retry
        was = cp.is_verified_active
        cp.subscription_status = status
        db.commit()
        _tell_access_change(db, cp, was)
    assert len(_got(db, amal, N.payment_failed)) == 1 and len(_got(db, amal, N.payment_activated)) == 1
    assert not _got(db, sami, N.payment_failed)  # no longer a member

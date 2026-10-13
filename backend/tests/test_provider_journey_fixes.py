"""Provider-journey audit fixes. Each test is one logic gap found in the
review of the service provider's journey, now corrected:

1. a provider whose documents are back under review keeps sight of its own
   offer (and so of its agreement and reviews) on the job page, and can
   answer the owner's clarification of it;
2. two checkouts can't both create a subscription, and an event about a
   subscription other than the one held doesn't change the provider's access;
3. a suspended, rejected or sent-back provider can still open billing to
   manage or cancel its subscription;
4. an offer's documents changed elsewhere (another tab, a colleague) after
   the page showed them are never submitted unseen;
5. whose requirement it is reaches a provider only with an award: no stable
   owner id on feed cards, requirement pages or amendments before then;
6. an offer that gave only a completion date, once that date passed, can't be
   awarded as it stands and is confirmed with a new completion date;
7. a provider that walks away from a deliverable the owner side left
   unanswered for 30 days isn't marked down for it;
8. reviews stay double-blind: once one side's review is published by time,
   the other can't answer it with its own; and a rating counts each owner's
   review of the latest completed job, not the one written last;
9. an admin-suspended offer can't be revised or withdrawn while offers are open;
10. a sealed tender doesn't tell competitors whether anyone has bid;
11. once offers have closed, the provider's own view of its offer lists the
    documents the owner received, not files attached since;
12. renewing a still-valid qualification keeps its approval counting until
    the renewal is decided (restored if the renewal is refused);
13. an organisation's eligibility rests on its own declared services and
    areas, not a colleague's personal ones from before joining;
14. a missing or expired qualification is offered as one to put right only
    when the provider can upload it;
15. after the representative role is handed over, the new representative
    can correct the organisation's identity (and only it is offered to);
16. a provider that was verified (or has offered) can't change who it is when
    sent back for a correction -- only correct its details;
17. a person removed from an organisation stops getting its requirement
    notices; colleagues who joined since get them;
18. an owner paper tied to a deliverable, added after the provider confirmed
    the terms, clears that confirmation like any other paper;
19. evidence is tied only to a progress update, where it shows;
20. one payment override at a time, and revoking ends it;
21. the provider is offered an answer to the owner's question only while it
    can still be answered;
22. the owner's 30 days to answer don't run while an admin has the
    requirement suspended."""
import time
from datetime import datetime, timedelta

import stripe

from app.config import get_settings
from app.models.category import ServiceCategory
from app.models.document import DocumentRequirement, ServiceProviderDocument
from app.models.enums import DocumentStatus, StakeholderType, UserRole
from app.models.enums import VerificationStatus
from app.models.agreement import Agreement, Milestone
from app.models.offer import Offer
from app.models.audit_log import AuditLog
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.review import Review
from app.services.tender_lifecycle import interested_providers
from app.models.project import Project
from app.services.reputation import provider_reputation
from app.services.tender_rules import kuwait_today
from tests.stage7_helpers import put_in_force
from tests.test_batch_a_contract_logic import _mv, _v
from tests.test_stage4_9_participation import _admin
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_batch_c_trust_accounts import _me
from tests.test_stage4_9_participation import _account, _when
from tests.test_organization_sharing import _organization
from tests.test_stage5_13_revise import DECL, _d, _submitted, _tender
from tests.test_stage9_6_billing import SECRET, _event, _post, _sub


def _standing(db, sp, status, suspended=False):
    profile = db.get(ServiceProviderProfile, _me(sp))
    profile.verification_status, profile.is_suspended = status, suspended
    db.commit()


def test_a_provider_under_re_review_keeps_its_offer_and_can_answer_for_it(db):
    owner = _account(db, "owner", "o-rereview-p@example.com")
    sp = _account(db, "service_provider", "s-rereview-p@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    q = owner.post(f"/owner/projects/{pid}/offers/{oid}/clarifications", json={"question": "Which cable brand?"}).json()["id"]
    _standing(db, sp, VerificationStatus.changes_requested)

    assert sp.get(f"/projects/{pid}/offers/mine").json()["id"] == oid
    assert sp.get(f"/projects/{pid}/offers/mine/history").status_code == 200
    assert [c["id"] for c in sp.get(f"/projects/{pid}/offers/mine/clarifications").json()] == [q]
    r = sp.post(f"/projects/{pid}/offers/mine/clarifications/{q}/answer", json={"answer": "Brand X"})
    assert r.status_code == 200, r.text
    # Putting the offer forward again still needs an approved account.
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 403


def test_the_winner_under_re_review_still_sees_its_offer_and_reviews(db):
    owner = _account(db, "owner", "o-rereview-w@example.com")
    sp = _account(db, "service_provider", "s-rereview-w@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    owner.post(f"/owner/projects/{pid}/offers/{oid}/approve")
    complete_transaction(owner, sp, pid)
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 5}).status_code == 200
    _standing(db, sp, VerificationStatus.pending_review)

    assert sp.get(f"/projects/{pid}/offers/mine").json()["status"] == "approved"  # the page shows the agreement on this
    assert sp.get(f"/service-provider/projects/{pid}/review").status_code == 200
    assert sp.get(f"/service-provider/projects/{pid}/review/received").status_code == 200
    # A suspended or rejected account still loses sight of it.
    _standing(db, sp, VerificationStatus.pending_review, suspended=True)
    assert sp.get(f"/projects/{pid}/offers/mine").status_code == 403
    _standing(db, sp, VerificationStatus.rejected)
    assert sp.get(f"/projects/{pid}/offers/mine").status_code == 403


class _Session(dict):
    def __init__(self, sid, url="https://stripe.test/c", status="open"):
        super().__init__(id=sid, status=status)
        self.id, self.url = sid, url


def test_two_checkouts_cant_both_subscribe_and_a_stray_event_leaves_access_alone(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", SECRET)
    monkeypatch.setattr(get_settings(), "stripe_price_id_monthly", "price_m")
    amal, sami, x_id, _ = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    cp = db.get(ServiceProviderProfile, x_id)
    cp.payment_override_active = False
    db.commit()
    sessions, expired = iter(["cs_A", "cs_B", "cs_C"]), []
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kw: _Session(next(sessions)))
    monkeypatch.setattr(stripe.checkout.Session, "expire", lambda sid: expired.append(sid))

    # Two colleagues open checkout: the first one's session is expired before the second starts.
    assert amal.post("/billing/checkout-session").status_code == 200
    assert sami.post("/billing/checkout-session").status_code == 200
    assert expired == ["cs_A"]

    # The second completes; the first can no longer be completed, but if Stripe still sent one
    # for another subscription, the live one held isn't swapped out.
    subs = {"sub_B": _sub("active", sub_id="sub_B"), "sub_A": _sub("active", sub_id="sub_A")}
    monkeypatch.setattr(stripe.Subscription, "retrieve", lambda sid: subs[sid])
    t0, meta = int(time.time()), {"service_provider_id": x_id}
    _post(_event("checkout.session.completed", {"object": "checkout.session", "id": "cs_B", "subscription": "sub_B", "customer": "cus_B", "metadata": meta}, t0, "e1"))
    _post(_event("checkout.session.completed", {"object": "checkout.session", "id": "cs_A", "subscription": "sub_A", "customer": "cus_A", "metadata": meta}, t0 + 1, "e2"))
    db.expire_all()
    cp = db.get(ServiceProviderProfile, x_id)
    assert (cp.stripe_subscription_id, cp.stripe_customer_id, cp.stripe_checkout_session_id) == ("sub_B", "cus_B", None)
    # The other subscription is cancelled in Stripe: its event leaves the held one's access alone.
    gone = _sub("canceled", sub_id="sub_A")
    gone["metadata"] = meta
    assert _post(_event("customer.subscription.deleted", gone, t0 + 10, "e3")).status_code == 200
    db.expire_all()
    cp = db.get(ServiceProviderProfile, x_id)
    assert cp.subscription_status.value == "active" and cp.is_verified_active


def test_a_checkout_that_already_completed_isnt_followed_by_another(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_price_id_monthly", "price_m")
    sp = _account(db, "service_provider", "s-checkout-done@example.com")
    db.get(ServiceProviderProfile, _me(sp)).payment_override_active = False
    db.commit()
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kw: _Session("cs_1"))
    assert sp.post("/billing/checkout-session").status_code == 200

    def cant_expire(sid):
        raise stripe.error.InvalidRequestError("already complete", None)

    monkeypatch.setattr(stripe.checkout.Session, "expire", cant_expire)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", lambda sid: _Session(sid, status="complete"))
    r = sp.post("/billing/checkout-session")  # before its webhook arrives
    assert r.status_code == 409 and "just set up" in r.json()["detail"]


def test_billing_stays_reachable_whatever_the_accounts_standing(db, monkeypatch):
    sp = _account(db, "service_provider", "s-portal@example.com")
    profile = db.get(ServiceProviderProfile, _me(sp))
    profile.stripe_customer_id = "cus_1"
    db.commit()
    monkeypatch.setattr(stripe.billing_portal.Session, "create", lambda **kw: _Session("bps_1", url="https://stripe.test/portal"))
    for status, suspended in ((VerificationStatus.changes_requested, False), (VerificationStatus.rejected, False), (VerificationStatus.approved, True)):
        _standing(db, sp, status, suspended)
        r = sp.post("/billing/portal-session")
        assert r.status_code == 200 and r.json()["url"] == "https://stripe.test/portal", (status, suspended, r.text)


def _tab(email):
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _seen(client, pid):
    return {"X-Offer-Documents": ",".join(sorted(d["token"] for d in client.get(f"/projects/{pid}/offers/documents").json()))}


def _upload(client, pid, name):
    return client.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": (name, b"%PDF-1", "application/pdf")})


def test_documents_changed_elsewhere_are_never_submitted_unseen(db):
    owner = _account(db, "owner", "o-docs-seen@example.com")
    tab1 = _account(db, "service_provider", "s-docs-seen@example.com")
    pid = _tender(owner)
    tab1.post(f"/projects/{pid}/participate")
    _upload(tab1, pid, "reviewed.pdf")
    saved = tab1.put(f"/projects/{pid}/offers/draft", json={"amount": "1000", "message": "M", "accepted_declarations": [DECL],
                                                               "proposed_start_date": _d(20), "proposed_duration_days": 30}).json()
    seen = _seen(tab1, pid)  # what tab 1 shows
    _upload(_tab("s-docs-seen@example.com"), pid, "unseen.pdf")  # another tab replaces it

    r = tab1.post(f"/projects/{pid}/offers/draft/submit", headers={"If-Match": str(saved["draft_version"]), **seen})
    assert r.status_code == 409 and "documents were changed" in r.json()["detail"]
    # Reloaded, it goes with what is now shown.
    r = tab1.post(f"/projects/{pid}/offers/draft/submit", headers={"If-Match": str(saved["draft_version"]), **_seen(tab1, pid)})
    assert r.status_code == 200, r.text
    offer = db.query(Offer).filter(Offer.project_id == pid).one()
    db.refresh(offer)
    assert [d["file_name"] for d in offer.submitted_documents] == ["unseen.pdf"]

    # Revising works the same way.
    seen = _seen(tab1, pid)
    _upload(_tab("s-docs-seen@example.com"), pid, "later.pdf")
    body = {"amount": "900", "message": "M2", "accepted_declarations": [DECL], "proposed_start_date": _d(20), "proposed_duration_days": 30}
    r = tab1.post(f"/projects/{pid}/offers", json=body, headers={"If-Match": str(r.json()["revision"]), **seen})
    assert r.status_code == 409 and "documents were changed" in r.json()["detail"]


def test_whose_requirement_it_is_reaches_a_provider_only_with_an_award(db):
    owner = _account(db, "owner", "o-who@example.com")
    winner = _account(db, "service_provider", "s-who-win@example.com")
    other = _account(db, "service_provider", "s-who-other@example.com")
    pid = _tender(owner, title="First job")
    _submitted(winner, pid)
    _submitted(other, pid)
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"title": "First job (gate)"}, headers={"If-Match": str(v)}).status_code == 200

    for sp in (winner, other):
        assert sp.get(f"/projects/{pid}").json()["owner_id"] is None
        cards = sp.get("/service-provider/feed").json()["items"]
        assert cards and all(c["owner_id"] is None for c in cards)
        assert [a["created_by"] for a in sp.get(f"/projects/{pid}/amendments").json()] == [None]
    assert owner.get(f"/projects/{pid}/amendments").json()[0]["created_by"] is not None  # the owner side still sees its own

    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{winner.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    assert winner.get(f"/projects/{pid}").json()["owner_id"] == _me(owner)  # awarded: theirs to know
    assert other.get(f"/projects/{pid}").json()["owner_id"] is None


def _awarded_to(db, owner, sp, title="Job"):
    pid = _tender(owner, title=title)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{sp.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    return pid


def test_a_completion_only_offer_past_its_date_is_restated_before_award(db):
    owner = _account(db, "owner", "o-done-by@example.com")
    sp = _account(db, "service_provider", "s-done-by@example.com")
    pid = _tender(owner)
    sp.post(f"/projects/{pid}/participate")
    sp.put(f"/projects/{pid}/offers/draft", json={"amount": "1000", "message": "M", "accepted_declarations": [DECL], "proposed_completion_date": _d(20)})
    sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("m.pdf", b"%PDF", "application/pdf")})
    assert sp.post(f"/projects/{pid}/offers/draft/submit").status_code == 200
    owner.post(f"/owner/projects/{pid}/close")
    offer = db.query(Offer).filter(Offer.project_id == pid).one()
    offer.proposed_completion_date = kuwait_today() - timedelta(days=3)  # evaluation ran past it
    db.commit()

    r = owner.post(f"/owner/projects/{pid}/offers/{offer.id}/approve")
    assert r.status_code == 409 and "completion date has already passed" in r.json()["detail"]
    assert sp.get(f"/projects/{pid}/offers/mine").json()["start_passed"] is True
    r = sp.post(f"/projects/{pid}/offers/confirm", json={"proposed_start_date": kuwait_today().isoformat()})
    assert r.status_code == 400 and "new completion date" in r.json()["detail"]
    new = (kuwait_today() + timedelta(days=25)).isoformat()
    r = sp.post(f"/projects/{pid}/offers/confirm", json={"proposed_completion_date": new})
    assert r.status_code == 200 and r.json()["proposed_completion_date"] == new and r.json()["proposed_start_date"] is None
    assert owner.post(f"/owner/projects/{pid}/offers/{offer.id}/approve").status_code == 200


def test_walking_away_from_a_deliverable_left_unanswered_isnt_marked_down(db):
    owner = _account(db, "owner", "o-undecided@example.com")
    sp = _account(db, "service_provider", "s-undecided@example.com")
    pid = _awarded_to(db, owner, sp)
    base = f"/projects/{pid}/agreement"
    mid = owner.post(f"{base}/milestones", json={"title": "Panels"}, headers=_v(owner, pid)).json()["milestones"][0]["id"]
    put_in_force(owner, sp, pid)
    sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid))
    assert sp.post(f"{base}/milestones/{mid}/deliver", json={}, headers=_mv(sp, pid, mid)).status_code == 200
    assert sp.get(base).json()["delivery_review_overdue"] is False
    db.get(Milestone, mid).delivered_at = datetime.utcnow() - timedelta(days=31)  # the owner side never answers
    db.commit()
    assert sp.get(base).json()["delivery_review_overdue"] is True
    assert sp.post(f"{base}/terminate", json={"reason": "No answer on the panels for a month"}, headers=_v(sp, pid)).status_code == 200
    assert provider_reputation(db, _me(sp)).terminated_transactions == 0


def test_a_review_published_by_time_cant_be_answered_with_one(db):
    owner = _account(db, "owner", "o-blind@example.com")
    sp = _account(db, "service_provider", "s-blind@example.com")
    pid = _awarded_to(db, owner, sp)
    complete_transaction(owner, sp, pid)
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 1, "comment": "Terrible"}).status_code == 200
    db.query(Review).update({Review.created_at: datetime.utcnow() - timedelta(days=15)})  # its sealed period passed
    db.commit()
    assert sp.get(f"/service-provider/projects/{pid}/review/received").json()["comment"] == "Terrible"
    r = sp.post("/service-provider/reviews", json={"project_id": pid, "rating": 1, "comment": "Retaliation"})
    assert r.status_code == 409 and "can no longer be reviewed" in r.json()["detail"]


def test_a_rating_counts_each_owners_review_of_its_latest_completed_job(db):
    owner = _account(db, "owner", "o-latest@example.com")
    sp = _account(db, "service_provider", "s-latest@example.com")
    older, newer = _awarded_to(db, owner, sp, "Older"), _awarded_to(db, owner, sp, "Newer")
    complete_transaction(owner, sp, older)
    complete_transaction(owner, sp, newer)
    db.query(Agreement).filter(Agreement.project_id == older).update({Agreement.completed_at: datetime.utcnow() - timedelta(days=60)})
    db.commit()
    assert owner.post("/owner/reviews", json={"project_id": newer, "rating": 5}).status_code == 200
    db.query(Review).update({Review.created_at: datetime.utcnow() - timedelta(hours=1)})
    db.commit()
    assert owner.post("/owner/reviews", json={"project_id": older, "rating": 1}).status_code == 200  # the older job, reviewed later
    db.query(Review).update({Review.revealed_at: datetime.utcnow()})
    db.commit()
    reputation = provider_reputation(db, _me(sp))
    assert (reputation.avg_rating, reputation.review_count) == (5.0, 1)


def test_a_suspended_offer_isnt_revised_or_withdrawn_while_open(db):
    owner = _account(db, "owner", "o-susp-offer@example.com")
    sp = _account(db, "service_provider", "s-susp-offer@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert _admin(db).post(f"/admin/offers/{mine['id']}/suspend", json={"suspended": True}).status_code == 200
    r = sp.post(f"/projects/{pid}/offers", json={"amount": "800", "message": "M2", "accepted_declarations": [DECL]}, headers={"If-Match": str(mine["revision"])})
    assert r.status_code == 400 and "suspended" in r.json()["detail"]
    r = sp.post(f"/projects/{pid}/offers/withdraw")
    assert r.status_code == 400 and "suspended" in r.json()["detail"]
    assert sp.get(f"/projects/{pid}/offers/mine").json()["withdrawals_left"] == 2


def test_a_sealed_tender_doesnt_say_whether_anyone_has_bid(db):
    owner = _account(db, "owner", "o-sealed-quiet@example.com")
    bidder = _account(db, "service_provider", "s-sealed-bidder@example.com")
    rival = _account(db, "service_provider", "s-sealed-rival@example.com")
    pid = _tender(owner, title="Sealed works", sealed=True)
    before = rival.get(f"/projects/{pid}").json()
    _submitted(bidder, pid)
    after = rival.get(f"/projects/{pid}").json()
    assert (before["tender_type_locked"], after["tender_type_locked"], after["offer_count"]) == (False, False, None)
    card = next(c for c in rival.get("/service-provider/feed").json()["items"] if c["id"] == pid)
    assert card["tender_type_locked"] is False
    assert owner.get(f"/projects/{pid}").json()["tender_type_locked"] is True  # the owner's own rule still holds


def test_after_the_close_the_providers_own_offer_lists_what_the_owner_received(db):
    owner = _account(db, "owner", "o-as-sent@example.com")
    sp = _account(db, "service_provider", "s-as-sent@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)  # with method-v1.pdf
    _upload(sp, pid, "method-v2.pdf")  # attached later, never put forward
    assert [d["file_name"] for d in sp.get(f"/projects/{pid}/offers/mine").json()["documents"]] == ["method-v2.pdf"]  # still open: what a revision sends
    owner.post(f"/owner/projects/{pid}/close")
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    oid = mine["id"]
    owners = owner.get(f"/owner/projects/{pid}/offers").json()
    received = next(o for o in owners if o["id"] == oid)["documents"]
    assert [d["file_name"] for d in mine["documents"]] == [d["file_name"] for d in received] == ["method-v1.pdf"]
    assert "/offers/mine/documents/file" in mine["documents"][0]["url"]  # opened through the provider's own route


def _qualification(db, **kw):
    lic = DocumentRequirement(name=kw.pop("name", "Licence"), applies_to=UserRole.service_provider, **kw)
    db.add(lic)
    db.commit()
    return lic


def _hold(db, sp, lic, expires, path="x/old.pdf"):
    d = db.query(ServiceProviderDocument).filter_by(service_provider_id=_me(sp), requirement_id=lic.id).first() \
        or ServiceProviderDocument(service_provider_id=_me(sp), requirement_id=lic.id)
    d.status, d.expires_on, d.file_path = DocumentStatus.approved, expires, path
    db.add(d)
    db.commit()


def _requiring(owner, **eligibility):
    pid = owner.post("/projects", data={"title": "Villa rewiring", "address": "Kaifan", "governorate": "ahmadi", "description": "Rewire.",
                                        "bid_deadline": _when(10)}).json()["id"]
    assert owner.put(f"/projects/{pid}/eligibility", json=eligibility).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def test_a_renewal_keeps_the_approval_it_renews_until_decided(db):
    owner = _account(db, "owner", "o-renew@example.com")
    sp = _account(db, "service_provider", "s-renew@example.com")
    admin = _admin(db)
    lic = _qualification(db, is_required=False, requires_expiry=True)
    valid_until = kuwait_today() + timedelta(days=20)
    _hold(db, sp, lic, valid_until)
    pid = _requiring(owner, qualifications=[lic.id])
    renew = lambda name: sp.post(f"/service-provider/documents/{lic.id}/upload", files={"file": (name, b"%PDF-1.4 x", "application/pdf")})  # noqa: E731

    assert renew("renewal.pdf").status_code == 200
    assert sp.get(f"/projects/{pid}/eligibility").json()["eligible"] is True  # the approval still counts
    # Refused: the approval it would have renewed stands, as it was.
    r = admin.post("/admin/review/documents", json={"service_provider_id": _me(sp), "requirement_id": lic.id, "decision": "rejected", "note": "Unreadable scan"})
    assert r.status_code == 200, r.text
    db.expire_all()
    doc = db.query(ServiceProviderDocument).filter_by(service_provider_id=_me(sp), requirement_id=lic.id).one()
    assert (doc.status, doc.file_path, doc.expires_on, doc.previous_file_path) == (DocumentStatus.approved, "x/old.pdf", valid_until, None)
    assert sp.get(f"/projects/{pid}/eligibility").json()["eligible"] is True
    # Renewed again and approved: the new file and expiry take over.
    assert renew("renewal-2.pdf").status_code == 200
    later = (kuwait_today() + timedelta(days=400)).isoformat()
    r = admin.post("/admin/review/documents", json={"service_provider_id": _me(sp), "requirement_id": lic.id, "decision": "approved", "expires_on": later})
    assert r.status_code == 200, r.text
    db.expire_all()
    doc = db.query(ServiceProviderDocument).filter_by(service_provider_id=_me(sp), requirement_id=lic.id).one()
    assert doc.status == DocumentStatus.approved and doc.file_path != "x/old.pdf" and doc.expires_on.isoformat() == later and doc.previous_file_path is None


def test_a_colleagues_personal_areas_dont_narrow_the_organisation(db):
    owner = _account(db, "owner", "o-areas@example.com")
    rep, colleague, org_id, _ = _organization(db, "service_provider", "Co W.L.L.", "rep@co.example", "col@co.example")
    profile = db.get(ServiceProviderProfile, org_id)
    profile.payment_override_active, profile.company_name, profile.service_governorates = True, "Co", []  # all of Kuwait
    db.query(ServiceProviderProfile).filter(ServiceProviderProfile.user_id == _me(colleague)).update({ServiceProviderProfile.service_governorates: ["capital"]})
    db.commit()  # what the colleague had set on its own account before joining
    pid = _requiring(owner, match_governorate=True)
    assert rep.get(f"/projects/{pid}/eligibility").json()["eligible"] is True
    assert pid in [c["id"] for c in rep.get("/service-provider/feed").json()["items"]]


def test_a_qualification_is_offered_to_put_right_only_when_it_can_be_uploaded(db):
    owner = _account(db, "owner", "o-fixable@example.com")
    sp = _account(db, "service_provider", "s-fixable@example.com")
    required = _qualification(db, name="Commercial licence", is_required=True, requires_expiry=True)
    _hold(db, sp, required, kuwait_today() - timedelta(days=1))  # expired; an approved account can't upload a required one
    orgs_only = _qualification(db, name="Grade certificate", is_required=False, applies_to_stakeholder=StakeholderType.organization)
    optional = _qualification(db, name="Safety certificate", is_required=False)
    retired = _qualification(db, name="Old permit", is_required=False)
    pid = _requiring(owner, qualifications=[required.id, orgs_only.id, optional.id, retired.id])
    retired.is_active = False
    db.commit()
    fixable = {r["name"]: r["fixable"] for r in sp.get(f"/projects/{pid}/eligibility").json()["reasons"]}
    assert fixable == {"Commercial licence": False, "Grade certificate": False, "Safety certificate": True, "Old permit": False}


def test_the_new_representative_can_correct_the_organisations_identity(db):
    founder, colleague, org_id, colleague_id = _organization(db, "service_provider", "X Contractng", "founder@x.example", "colleague@x.example")
    assert founder.post(f"/account/organization/representative/{colleague_id}").status_code == 200
    profile = db.get(ServiceProviderProfile, org_id)
    profile.verification_status = VerificationStatus.changes_requested  # "legal name must match the licence"
    db.commit()
    assert colleague.get("/account/identity").json()["stakeholder"]["editable"] is True
    assert founder.get("/account/identity").json()["stakeholder"]["editable"] is False  # now a member
    body = {"type": "organization", "legal_name": "X Contracting", "authorized": True}
    assert founder.put("/account/stakeholder", json=body).status_code in (403, 409)
    r = colleague.put("/account/stakeholder", json=body)
    assert r.status_code == 200, r.text
    assert colleague.get("/account/identity").json()["stakeholder"]["organization"]["legal_name"] == "X Contracting"
    # A member can't turn the organisation into an individual.
    assert colleague.put("/account/stakeholder", json={"type": "individual"}).status_code == 409


def test_a_verified_provider_sent_back_cant_change_who_it_is(db):
    owner = _account(db, "owner", "o-who-is@example.com")
    sp = _account(db, "service_provider", "s-who-is@example.com", organization="Solo W.L.L.")
    pid = _tender(owner)
    _submitted(sp, pid)
    _standing(db, sp, VerificationStatus.changes_requested)  # a document sent back for correction
    r = sp.put("/account/stakeholder", json={"type": "individual"})
    assert r.status_code == 409
    assert sp.get("/account/identity").json()["stakeholder"]["type"] == "organization"
    # Its details can still be corrected.
    assert sp.put("/account/stakeholder", json={"type": "organization", "legal_name": "Solo Contracting W.L.L.", "authorized": True}).status_code == 200


def test_a_removed_member_stops_getting_the_organisations_requirement_notices(db):
    owner = _account(db, "owner", "o-removed@example.com")
    rep, member, org_id, member_id = _organization(db, "service_provider", "Co W.L.L.", "rep@removed.example", "member@removed.example")
    profile = db.get(ServiceProviderProfile, org_id)
    profile.payment_override_active, profile.company_name = True, "Co"
    db.commit()
    pid = _tender(owner)
    link = f"/service-provider/projects/{pid}/offer"
    db.add_all([Notification(user_id=uid, type=NotificationType.new_requirement, title="New", body="New", link=link) for uid in (org_id, member_id)])
    db.commit()
    assert {u.id for u in interested_providers(db, db.get(Project, pid))} == {org_id, member_id}
    assert rep.delete(f"/account/organization/members/{member_id}").status_code == 200
    assert {u.id for u in interested_providers(db, db.get(Project, pid))} == {org_id}


def test_a_deliverable_paper_after_confirmation_needs_confirming_again(db):
    owner = _account(db, "owner", "o-paper@example.com")
    sp = _account(db, "service_provider", "s-paper@example.com")
    pid = _awarded_to(db, owner, sp)
    base = f"/projects/{pid}/agreement"
    mid = owner.post(f"{base}/milestones", json={"title": "Panels"}, headers=_v(owner, pid)).json()["milestones"][0]["id"]
    owner.patch(base, json={"effective_date": kuwait_today().isoformat()}, headers=_v(owner, pid))
    assert sp.post(f"{base}/confirm", headers=_v(sp, pid)).json()["provider_confirmed_at"] is not None
    r = owner.post(f"{base}/documents", data={"kind": "agreed_scope", "milestone_id": mid}, files={"file": ("scope.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json()["provider_confirmed_at"] is None
    assert owner.post(f"{base}/activate", headers=_v(owner, pid)).status_code != 200


def test_evidence_is_tied_only_to_a_progress_update(db):
    owner = _account(db, "owner", "o-evidence@example.com")
    sp = _account(db, "service_provider", "s-evidence@example.com")
    pid = _awarded_to(db, owner, sp)
    base = f"/projects/{pid}/agreement"
    put_in_force(owner, sp, pid)
    sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid))
    from app.models.agreement import ExecutionUpdate

    in_force = {"id": db.query(ExecutionUpdate.id).filter(ExecutionUpdate.kind == "in_force").scalar()}  # a history entry, not progress
    started = next(h for h in sp.get(base).json()["execution_history"] if h["kind"] == "started")
    upload = lambda update: sp.post(f"{base}/documents", data={"kind": "progress_photo", "execution_update_id": update},  # noqa: E731
                                     files={"file": ("p.jpg", b"\xff\xd8x", "image/jpeg")})
    r = upload(in_force["id"])
    assert r.status_code == 400 and "progress update" in r.json()["detail"]
    assert upload(started["id"]).status_code == 200


def test_one_payment_override_at_a_time(db):
    sp = _account(db, "service_provider", "s-override@example.com", paid=False)
    admin = _admin(db)
    url = f"/admin/service-providers/{_me(sp)}/payment-override"
    assert admin.post(url, json={"reason": "Pilot"}).status_code == 200
    assert admin.post(url, json={"reason": "Again"}).status_code == 409
    assert admin.post(f"{url}/revoke", json={"reason": "Ended"}).status_code == 200
    assert all(o["revoked_at"] for o in admin.get(f"/admin/service-providers/{_me(sp)}/payment-overrides").json())
    assert admin.post(f"{url}/revoke", json={}).status_code == 409


def test_the_answer_form_only_while_the_question_can_be_answered(db):
    owner = _account(db, "owner", "o-answerable@example.com")
    sp = _account(db, "service_provider", "s-answerable@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    owner.post(f"/owner/projects/{pid}/offers/{oid}/clarifications", json={"question": "Which brand?"})
    assert [q["answerable"] for q in sp.get(f"/projects/{pid}/offers/mine/clarifications").json()] == [True]
    owner.post(f"/owner/projects/{pid}/no-award", json={})
    assert [q["answerable"] for q in sp.get(f"/projects/{pid}/offers/mine/clarifications").json()] == [False]


def test_the_owners_30_days_dont_run_while_the_requirement_is_suspended(db):
    owner = _account(db, "owner", "o-paused-clock@example.com")
    sp = _account(db, "service_provider", "s-paused-clock@example.com")
    pid = _awarded_to(db, owner, sp)
    base = f"/projects/{pid}/agreement"
    put_in_force(owner, sp, pid)
    sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid))
    assert sp.post(f"{base}/completion/submit", json={}, headers=_v(sp, pid)).status_code == 200
    now = datetime.utcnow()
    db.query(Agreement).filter(Agreement.project_id == pid).update({Agreement.completion_submitted_at: now - timedelta(days=31)})
    # Suspended by an admin for 20 of those days (now lifted): the owner could answer for only 11.
    db.add_all([
        AuditLog(action="project.suspend", target_type="project", target_id=pid, created_at=now - timedelta(days=28)),
        AuditLog(action="project.reactivate", target_type="project", target_id=pid, created_at=now - timedelta(days=8)),
    ])
    db.commit()
    assert sp.get(base).json()["completion_review_overdue"] is False
    assert sp.post(f"{base}/terminate", json={"reason": "No answer"}, headers=_v(sp, pid)).status_code == 409
    db.query(Agreement).filter(Agreement.project_id == pid).update({Agreement.completion_submitted_at: now - timedelta(days=51)})
    db.commit()
    assert sp.get(base).json()["completion_review_overdue"] is True

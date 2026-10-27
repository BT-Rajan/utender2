"""The end-to-end usability run: each test is one place a person got stuck or
was misled, now corrected on the server side."""
from app.models.audit_log import AuditLog
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.user import User
from tests.stage7_helpers import put_in_force
from tests.test_stage4_9_participation import _account, _admin, _when
from tests.test_stage5_13_revise import _submitted, _tender


def _me(c):
    return c.get("/auth/me").json()["id"]


def _pending_owner(db, email):
    """Verification submitted, not yet decided."""
    owner = _account(db, "owner", email, approve=False)
    profile = db.get(OwnerProfile, _me(owner))
    profile.verification_status = VerificationStatus.pending_review
    db.commit()
    return owner


def _draft(owner, status="draft"):
    return owner.post("/projects", data={"title": "Roof", "address": "Salwa", "description": "Waterproof a roof.", "bid_deadline": _when(10), "status": status})


def test_an_owner_under_review_prepares_drafts_but_publishes_only_once_approved(db):
    owner = _pending_owner(db, "pending@owner.example")
    r = _draft(owner)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    version = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"title": "Roof, phase 1"}, headers={"If-Match": str(version)}).status_code == 200
    # Publishing -- at creation or later -- waits for approval.
    assert _draft(owner, status="open").status_code == 403
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 403
    # The draft is still the owner's to discard.
    assert owner.post(f"/owner/projects/{pid}/discard").status_code == 200


def test_an_owner_who_has_not_submitted_or_was_rejected_cannot_draft(db):
    unsubmitted = _account(db, "owner", "new@owner.example", approve=False)
    assert _draft(unsubmitted).status_code == 403
    rejected = _pending_owner(db, "rejected@owner.example")
    db.get(OwnerProfile, _me(rejected)).verification_status = VerificationStatus.rejected
    db.commit()
    assert _draft(rejected).status_code == 403


def test_a_verified_provider_without_online_payment_can_ask_for_access(db):
    admin = _admin(db)
    sp = _account(db, "service_provider", "waiting@sp.example", paid=False)
    assert sp.get("/billing/access-request").json() == {"requested_at": None}
    first = sp.post("/billing/access-request")
    assert first.status_code == 200 and first.json()["requested_at"]
    # Asking again while it waits adds nothing.
    assert sp.post("/billing/access-request").json() == first.json()
    assert db.query(AuditLog).filter(AuditLog.action == "marketplace_access.requested").count() == 1
    attention = {a["kind"]: a for a in admin.get("/admin/overview").json()["attention"]["data"]}
    assert attention["access_requested"]["items"][0]["id"] == _me(sp)
    # Access granted: the request is answered, and asking again is refused.
    assert admin.post(f"/admin/service-providers/{_me(sp)}/payment-override", json={"reason": "Pilot."}).status_code == 200
    assert sp.get("/billing/access-request").json() == {"requested_at": None}
    assert "access_requested" not in {a["kind"] for a in admin.get("/admin/overview").json()["attention"]["data"]}
    assert sp.post("/billing/access-request").status_code == 409


def test_an_unverified_provider_cannot_ask_for_access(db):
    sp = _account(db, "service_provider", "unverified@sp.example", approve=False)
    assert sp.post("/billing/access-request").status_code == 403


def test_questions_close_when_offers_close_early(db):
    owner = _account(db, "owner", "early@owner.example")
    sp = _account(db, "service_provider", "early@sp.example")
    pid = _tender(owner)
    _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    detail = owner.get(f"/projects/{pid}").json()
    assert detail["tender_rules"]["questions_close_at"] == detail["closed_at"]


def test_the_history_shows_the_owner_changing_confirmed_terms(db):
    owner = _account(db, "owner", "terms@owner.example")
    sp = _account(db, "service_provider", "terms@sp.example")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    offer_id = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve").status_code == 200
    base = f"/projects/{pid}/agreement"

    def v(c):
        return {"If-Match": str(c.get(base).json()["version"])}

    from app.clock import kuwait_today

    assert owner.patch(base, json={"effective_date": kuwait_today().isoformat()}, headers=v(owner)).status_code == 200
    assert sp.post(f"{base}/confirm", headers=v(sp)).status_code == 200
    assert owner.patch(base, json={"reference": "PO-118"}, headers=v(owner)).status_code == 200
    kinds = [e["kind"] for e in owner.get(base).json()["timeline"]]
    assert kinds[kinds.index("terms_confirmed") + 1] == "terms_changed"
    put_in_force(owner, sp, pid)
    kinds = [e["kind"] for e in sp.get(base).json()["timeline"]]
    assert kinds.count("terms_confirmed") == 2 and kinds.count("terms_changed") == 1


def test_the_overview_counts_owners_not_admins_who_signed_up_as_one(db):
    admin = _admin(db)
    _account(db, "owner", "real@owner.example")
    promoted = _account(db, "owner", "promoted@owner.example")
    db.get(User, _me(promoted)).role = "admin"
    db.commit()
    assert admin.get("/admin/overview").json()["accounts"]["data"]["owners"]["total"] == 1


def test_a_clarification_notice_opens_at_the_question(db):
    """Second run: the owner's question sits low on a long page; its notice
    links straight to it."""
    from app.models.enums import NotificationType
    from app.models.notification import Notification

    owner = _account(db, "owner", "clar@owner.example")
    sp = _account(db, "service_provider", "clar@sp.example")
    pid = _tender(owner)
    offer_id = _submitted(sp, pid)["id"]
    owner.post(f"/owner/projects/{pid}/close")
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/clarifications", json={"question": "Which membrane brand?"}).status_code in (200, 201)
    notice = db.query(Notification).filter(Notification.user_id == _me(sp), Notification.type == NotificationType.offer_clarification_requested).one()
    assert notice.link == f"/service-provider/projects/{pid}/offer#offer-clarifications"


def test_the_overview_says_when_no_support_contact_is_set(db):
    """Dead ends: every "contact support" message shows the support contact;
    until an admin sets it, the overview says so."""
    admin = _admin(db)

    def flagged():
        return "support_contact_missing" in {a["kind"] for a in admin.get("/admin/overview").json()["attention"]["data"]}

    assert flagged()
    assert admin.put("/admin/cms/support_contact/en", json={"value": "support@u-tender.example · +965 2222 0000"}).status_code == 200
    assert not flagged()


def test_a_rejected_organization_cannot_invite_colleagues(db):
    sp = _account(db, "service_provider", "rejected-rep@sp.example", organization="Rejected Co")
    from app.models.service_provider import ServiceProviderProfile

    db.get(ServiceProviderProfile, _me(sp)).verification_status = VerificationStatus.rejected
    db.commit()
    r = sp.post("/account/organization/invitations", json={"email": "colleague@rejected.example"})
    assert r.status_code == 409 and "rejected or suspended" in r.json()["detail"]

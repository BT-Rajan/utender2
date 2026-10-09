"""Stage 6.13: award decision. The owner side awards one live offer on its own
requirement, once offers have closed: one authoritative award (record, offer
statuses, requirement status) in one transaction, never on a suspended
requirement, never silently on an offer priced against an earlier version;
the offers themselves, the shortlist and the notes stay as they were."""
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import NotificationType, OfferStatus, ProjectStatus
from app.models.evaluation_note import EvaluationNote
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.offer_shortlist import OfferShortlist
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _submitted, _tender


def _offer_id(db, pid, sp):
    me = sp.get("/auth/me").json()["id"]
    return db.query(Offer).filter(Offer.project_id == pid, Offer.service_provider_id == me).one().id


def _award(owner, pid, offer_id, **body):
    return owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve", json=body or None)


def test_one_authoritative_award_and_nothing_else_rewritten(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana"))
    pid = _tender(owner)
    for sp in (a, b, c):
        _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    a_offer, b_offer, c_offer = (_offer_id(db, pid, sp) for sp in (a, b, c))
    # B and C shortlisted, a note on B: the award goes to A (shortlisting isn't required).
    owner.put(f"/owner/projects/{pid}/offers/{b_offer}/shortlist")
    owner.put(f"/owner/projects/{pid}/offers/{c_offer}/shortlist")
    owner.post(f"/owner/projects/{pid}/notes", json={"body": "Good programme.", "offer_id": b_offer})
    before = {o.id: (o.amount, o.message, o.assumptions, o.proposed_duration_days, o.submitted_documents, o.revision) for o in db.query(Offer)}
    r = _award(owner, pid, a_offer)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "awarded"
    db.expire_all()
    # The decision: requirement awarded; A approved; B and C not selected; one award record, with its context.
    assert db.get(Project, pid).status == ProjectStatus.awarded
    assert {o.id: o.status for o in db.query(Offer)} == {a_offer: OfferStatus.approved, b_offer: OfferStatus.rejected, c_offer: OfferStatus.rejected}
    (record,) = db.query(AwardRecord).filter(AwardRecord.project_id == pid).all()
    assert (record.offer_id, record.offer_revision, record.amount) == (a_offer, 1, db.get(Offer, a_offer).amount)
    assert record.awarded_by == owner.get("/auth/me").json()["id"]
    # Who and when, in the audit log; winner and others told through the existing notifications.
    assert db.query(AuditLog).filter(AuditLog.target_id == pid, AuditLog.action == "project.award").count() == 1
    a_id, b_id = a.get("/auth/me").json()["id"], b.get("/auth/me").json()["id"]
    assert db.query(Notification).filter(Notification.user_id == a_id, Notification.type == NotificationType.award_won).count() == 1
    assert db.query(Notification).filter(Notification.user_id == b_id, Notification.type == NotificationType.award_lost).count() == 1
    # The offers' content, the shortlist and the notes are untouched.
    assert {o.id: (o.amount, o.message, o.assumptions, o.proposed_duration_days, o.submitted_documents, o.revision) for o in db.query(Offer)} == before
    assert {s.offer_id for s in db.query(OfferShortlist)} == {b_offer, c_offer}
    assert [n.body for n in db.query(EvaluationNote)] == ["Good programme."]
    # Unambiguous to the owner: the award and the winner.
    award = owner.get(f"/projects/{pid}/award").json()
    assert (award["offer_id"], award["service_provider_company_name"]) == (a_offer, "amal")
    # Final: no second award (a retry, a stale tab, another offer), no new or changed offers.
    for offer_id in (a_offer, b_offer):
        assert _award(owner, pid, offer_id).status_code == 400
    assert db.query(AwardRecord).filter(AwardRecord.project_id == pid).count() == 1
    assert b.post(f"/projects/{pid}/offers", json={"amount": "1"}, headers={"If-Match": "1"}).status_code == 400
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    assert owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "not_needed"}).status_code == 400


def test_only_the_owner_side_awards_its_own_requirements_live_offers(db):
    owner = _account(db, "owner", "owner@example.com")
    stranger = _account(db, "owner", "stranger@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid, other = _tender(owner, "Mine"), _tender(stranger, "Theirs")
    _submitted(a, pid)
    _submitted(b, pid)
    _submitted(b, other)
    assert _award(owner, pid, _offer_id(db, pid, a)).status_code == 400  # still open: close first
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    for p, o in ((pid, owner), (other, stranger)):
        assert o.post(f"/owner/projects/{p}/close").status_code == 200
    a_offer, b_offer, other_offer = _offer_id(db, pid, a), _offer_id(db, pid, b), _offer_id(db, other, b)
    assert _award(a, pid, a_offer).status_code == 403  # a provider can't award, even its own
    assert _award(stranger, pid, a_offer).status_code == 404
    assert _award(owner, pid, other_offer).status_code == 404  # another requirement's offer
    assert _award(owner, pid, b_offer).status_code == 400  # withdrawn
    # Admin-suspended: no decision on it meanwhile.
    admin = _admin(db)
    assert admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True}).status_code == 200
    assert _award(owner, pid, a_offer).status_code == 400
    assert admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": False}).status_code == 200
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.closed and db.query(AwardRecord).count() == 0
    assert _award(owner, pid, a_offer).status_code == 200


def test_an_offer_on_an_earlier_version_is_awarded_only_knowingly(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    _submitted(a, pid)
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Substation plus a second bay."}, headers={"If-Match": str(v)})
    _submitted(b, pid)  # against the amended version
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    a_offer = _offer_id(db, pid, a)
    r = _award(owner, pid, a_offer)
    assert r.status_code == 409 and "earlier version" in r.json()["detail"]
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.closed and db.query(AwardRecord).count() == 0
    assert db.get(Offer, a_offer).status == OfferStatus.submitted
    # Batch B: the owner's word alone is no longer enough; the acknowledgement is refused.
    r = _award(owner, pid, a_offer, acknowledge_earlier_version=True)
    assert r.status_code == 409 and "Ask the provider to confirm it still stands" in r.json()["detail"]  # Batch B:
    db.expire_all()
    assert db.query(AwardRecord).count() == 0 and db.get(Offer, a_offer).status == OfferStatus.submitted  # Batch B:
    # Batch B: once its provider confirms it still stands (allowed after the close), it can be awarded.
    assert a.post(f"/projects/{pid}/offers/confirm").status_code == 200  # Batch B:
    assert _award(owner, pid, a_offer).status_code == 200  # Batch B:
    # An offer on the current version needs no such confirmation (elsewhere).
    p2 = _tender(owner, "Current")
    _submitted(b, p2)
    owner.post(f"/owner/projects/{p2}/close")
    assert _award(owner, p2, _offer_id(db, p2, b)).status_code == 200


def test_cancelled_or_ended_first_means_no_award(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    for end, body in (("cancel", {"reason": "not_needed"}), ("close-externally", {})):
        pid = _tender(owner, end)
        _submitted(a, pid)
        owner.post(f"/owner/projects/{pid}/close")
        assert owner.post(f"/owner/projects/{pid}/{end}", json=body).status_code == 200
        assert _award(owner, pid, _offer_id(db, pid, a)).status_code == 400
        assert db.query(AwardRecord).filter(AwardRecord.project_id == pid).count() == 0

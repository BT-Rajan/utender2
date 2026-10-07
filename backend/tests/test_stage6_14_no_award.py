"""Stage 6.14: concluding without an award -- no suitable offer, ended outside
U-Tender, or cancelled -- on the existing lifecycle: one final outcome, under
the requirement's lock; nobody awarded; offers, shortlist and notes kept;
terminal states never reopened or overwritten; not while admin-suspended."""
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

ENDINGS = {"no-award": {"note": "All prices above budget."}, "close-externally": {}, "cancel": {"reason": "postponed"}}


def _offer_id(db, pid, sp):
    me = sp.get("/auth/me").json()["id"]
    return db.query(Offer).filter(Offer.project_id == pid, Offer.service_provider_id == me).one().id


def test_no_suitable_offer_concludes_it_and_keeps_everything(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    a_offer = _offer_id(db, pid, a)
    owner.put(f"/owner/projects/{pid}/offers/{a_offer}/shortlist")
    owner.post(f"/owner/projects/{pid}/notes", json={"body": "Closest, still too expensive.", "offer_id": a_offer})
    before = {o.id: (o.status, o.amount, o.message, o.submitted_documents, o.revision, o.updated_at) for o in db.query(Offer)}
    r = owner.post(f"/owner/projects/{pid}/no-award", json={"note": "All prices above budget."})
    assert r.status_code == 200, r.text
    db.expire_all()
    p = db.get(Project, pid)
    assert (p.status, p.closure_reason, p.closure_note) == (ProjectStatus.no_award, "no_suitable_offer", "All prices above budget.")
    # Nobody awarded; offers, shortlist, notes exactly as they were; still readable by the owner.
    assert db.query(AwardRecord).count() == 0
    assert {o.id: (o.status, o.amount, o.message, o.submitted_documents, o.revision, o.updated_at) for o in db.query(Offer)} == before
    assert all(o.status == OfferStatus.submitted for o in db.query(Offer))
    assert [s.offer_id for s in db.query(OfferShortlist)] == [a_offer] and db.query(EvaluationNote).count() == 1
    assert len(owner.get(f"/owner/projects/{pid}/offers").json()) == 2
    assert owner.get(f"/owner/projects/{pid}/offers/{a_offer}").status_code == 200
    # Recorded (who, what, why); bidders told through the existing notifications.
    entry = db.query(AuditLog).filter(AuditLog.target_id == pid, AuditLog.action == "project.no_award").one()
    assert entry.new_value == "no_award:no_suitable_offer" and entry.reason == "All prices above budget."
    assert db.query(Notification).filter(Notification.type == NotificationType.tender_no_award).count() == 2
    # Final: no new or changed offers, no award, no other ending, no repeat.
    assert b.post(f"/projects/{pid}/offers", json={"amount": "1"}, headers={"If-Match": "1"}).status_code == 400
    assert owner.post(f"/owner/projects/{pid}/offers/{a_offer}/approve").status_code == 400
    assert owner.put(f"/owner/projects/{pid}/offers/{a_offer}/shortlist").status_code == 400
    for action, body in ENDINGS.items():
        assert owner.post(f"/owner/projects/{pid}/{action}", json=body).status_code == 400, action
    db.expire_all()
    assert (db.get(Project, pid).status, db.get(Project, pid).closure_reason) == (ProjectStatus.no_award, "no_suitable_offer")


def test_terminal_outcomes_are_never_overwritten(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    # Awarded: no ending overwrites it.
    awarded = _tender(owner, "Awarded")
    _submitted(a, awarded)
    owner.post(f"/owner/projects/{awarded}/close")
    assert owner.post(f"/owner/projects/{awarded}/offers/{_offer_id(db, awarded, a)}/approve").status_code == 200
    for action, body in ENDINGS.items():
        assert owner.post(f"/owner/projects/{awarded}/{action}", json=body).status_code == 400, action
    # Cancelled, ended outside U-Tender: final too, and never awarded afterwards.
    for first in ("cancel", "close-externally"):
        pid = _tender(owner, first)
        _submitted(a, pid)
        assert owner.post(f"/owner/projects/{pid}/{first}", json=ENDINGS[first]).status_code == 200
        for action, body in ENDINGS.items():
            assert owner.post(f"/owner/projects/{pid}/{action}", json=body).status_code == 400, (first, action)
        assert owner.post(f"/owner/projects/{pid}/offers/{_offer_id(db, pid, a)}/approve").status_code == 400
    # Open: "no suitable offer" needs offers to have closed first; cancelling or ending outside U-Tender doesn't.
    open_pid = _tender(owner, "Open")
    assert owner.post(f"/owner/projects/{open_pid}/no-award", json={}).status_code == 400
    db.expire_all()
    assert db.query(Project).filter(Project.status == ProjectStatus.awarded).count() == 1
    assert db.query(AwardRecord).count() == 1


def test_only_the_owner_side_and_not_while_suspended(db):
    owner = _account(db, "owner", "owner@example.com")
    stranger = _account(db, "owner", "stranger@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    owner.post(f"/owner/projects/{pid}/close")
    for action, body in ENDINGS.items():
        assert a.post(f"/owner/projects/{pid}/{action}", json=body).status_code == 403, action
        assert stranger.post(f"/owner/projects/{pid}/{action}", json=body).status_code == 404, action
    admin = _admin(db)
    assert admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True}).status_code == 200
    for action, body in ENDINGS.items():
        r = owner.post(f"/owner/projects/{pid}/{action}", json=body)
        assert r.status_code == 400 and "suspended" in r.json()["detail"], action
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.closed
    assert admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": False}).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/no-award", json={}).status_code == 200

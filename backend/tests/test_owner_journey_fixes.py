"""Owner-journey audit fixes. Each test is one logic gap found in the review
of the owner's journey, now corrected:

1. a sealed tender's invitation doesn't tell the owner who has bid;
2. a party whose documents are back under review keeps the job page;
3. an offer whose proposed start date passed during evaluation can be
   confirmed with a new start date, then awarded;
4. a terminated agreement can be started again as a similar requirement;
5. publishing moves the requirement's version on, so a colleague's stale
   draft page can't write to the live requirement;
6. (frontend) the amend form sends only its own changes, against the version
   it was filled from;
7. a provider organisation can be invited and awarded after its founding
   account is deactivated, while someone still acts for it;
8. a published answer's files can't be added to afterwards, and a
   colleague's files from an answer that never went in aren't part of it;
9. an answered question stays tied to the change it brought about;
10. the deadline reminder is sent again before an extended deadline;
11. "close early" after the deadline is the deadline's own close, not an early one;
12. a suspended owner can't publish answers;
13. a draft whose deadline passed is refused the same way by every editor,
    with a way forward;
14. an agreed change can't move the completion date before open deliverables;
15. the owner side is told when offers close, when nobody bid, and when a
    provider confirms its offer."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.main import app
from app.models.audit_log import AuditLog
from app.models.offer import Offer, OfferRevision
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.services.tender_rules import kuwait_today
from tests.test_batch_a_contract_logic import _v
from tests.stage7_helpers import put_in_force
from tests.test_batch_c_trust_accounts import _completed, _me
from tests.test_stage4_9_participation import _account, _admin
from tests.test_organization_sharing import _organization
from tests.test_stage5_13_revise import DECL, _submitted, _tender, _when


def _invitations(db, sp):
    return db.query(Notification).filter(Notification.user_id == _me(sp), Notification.type == NotificationType.requirement_invitation).count()


def test_a_sealed_invitation_answers_the_same_whether_or_not_the_provider_bid(db):
    owner = _account(db, "owner", "o-seal-inv@example.com")
    bidder = _account(db, "service_provider", "s-seal-bid@example.com")
    other = _account(db, "service_provider", "s-seal-other@example.com")
    _completed(db, owner, bidder, "First job")
    _completed(db, owner, other, "Second job")
    pid = _tender(owner, title="Sealed job", sealed=True)
    _submitted(bidder, pid)

    for sp in (bidder, other):
        assert owner.post(f"/owner/projects/{pid}/invitations/{_me(sp)}").status_code == 204
    for sp in (bidder, other):
        r = owner.post(f"/owner/projects/{pid}/invitations/{_me(sp)}")
        assert r.status_code == 409 and "already been invited" in r.json()["detail"]
    # The bidder isn't sent an invitation to what it already offered on.
    assert _invitations(db, bidder) == 0 and _invitations(db, other) == 1

    # Owner-visible: identities are already shown, so the owner is told.
    visible = _tender(owner, title="Open job")
    _submitted(bidder, visible)
    r = owner.post(f"/owner/projects/{visible}/invitations/{_me(bidder)}")
    assert r.status_code == 409 and "already made an offer" in r.json()["detail"]


def test_an_offer_whose_start_date_passed_is_confirmed_with_a_new_one_then_awarded(db):
    owner = _account(db, "owner", "o-start@example.com")
    sp = _account(db, "service_provider", "s-start@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    # The start date passes while the owner evaluates; this one gave a completion date.
    offer = db.get(Offer, oid)
    old_start = kuwait_today() - timedelta(days=2)
    offer.proposed_start_date, offer.proposed_duration_days, offer.proposed_completion_date = old_start, None, old_start + timedelta(days=30)
    db.commit()

    row = next(o for o in owner.get(f"/owner/projects/{pid}/offers").json() if o["id"] == oid)
    assert row["start_passed"] is True
    assert owner.post(f"/owner/projects/{pid}/offers/{oid}/approve").status_code == 409
    # The owner can ask; the provider is told the start date passed.
    assert owner.post(f"/owner/projects/{pid}/offers/{oid}/request-confirmation").status_code == 200
    assert sp.get(f"/projects/{pid}/offers/mine").json()["start_passed"] is True

    r = sp.post(f"/projects/{pid}/offers/confirm")
    assert r.status_code == 400 and "Give a new start date" in r.json()["detail"]
    r = sp.post(f"/projects/{pid}/offers/confirm", json={"proposed_start_date": (kuwait_today() - timedelta(days=1)).isoformat()})
    assert r.status_code == 400 and "can't be in the past" in r.json()["detail"]
    new_start = kuwait_today() + timedelta(days=5)
    r = sp.post(f"/projects/{pid}/offers/confirm", json={"proposed_start_date": new_start.isoformat()})
    assert r.status_code == 200, r.text
    mine = r.json()
    # The same span of work follows the new start; the earlier dates stay in the history.
    assert mine["start_passed"] is False and mine["proposed_start_date"] == new_start.isoformat()
    assert mine["proposed_completion_date"] == (new_start + timedelta(days=30)).isoformat()
    assert db.query(OfferRevision).filter(OfferRevision.offer_id == oid, OfferRevision.proposed_start_date == old_start).count() == 1
    # Once restated, its date can't be restated again; and now it can be awarded.
    r = sp.post(f"/projects/{pid}/offers/confirm", json={"proposed_start_date": (new_start + timedelta(days=1)).isoformat()})
    assert r.status_code == 400
    assert owner.post(f"/owner/projects/{pid}/offers/{oid}/approve").status_code == 200


def test_a_new_start_date_is_given_by_revising_while_bidding_is_open(db):
    owner = _account(db, "owner", "o-start-open@example.com")
    sp = _account(db, "service_provider", "s-start-open@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    r = sp.post(f"/projects/{pid}/offers/confirm", json={"proposed_start_date": (kuwait_today() + timedelta(days=30)).isoformat()})
    assert r.status_code == 400 and "revising" in r.json()["detail"]


def test_a_terminated_agreement_can_be_started_again_as_a_new_draft(db):
    owner = _account(db, "owner", "o-term@example.com")
    sp = _account(db, "service_provider", "s-term@example.com")
    pid = _tender(owner, title="Roof repair")
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{oid}/approve").status_code == 200
    # Awarded and still in progress: not yet.
    assert owner.post(f"/owner/projects/{pid}/restart", json={}).status_code == 400
    assert sp.post(f"/projects/{pid}/agreement/terminate", json={"reason": "We cannot take this job"}, headers=_v(sp, pid)).status_code == 200

    r = owner.post(f"/owner/projects/{pid}/restart", json={})
    assert r.status_code == 201, r.text
    draft = r.json()
    assert draft["status"] == "draft" and draft["title"] == "Roof repair" and draft["id"] != pid
    # The terminated one stays as it ended.
    old = owner.get(f"/projects/{pid}").json()
    assert old["status"] == "awarded" and old["transaction_status"] == "terminated"


def test_a_colleagues_stale_draft_page_cant_write_to_the_published_requirement(db):
    a, b, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "a-stale@gulf.example", "b-stale@gulf.example")
    pid = a.post("/projects", data={"title": "Boundary wall", "address": "Kaifan", "description": "A 60 m block wall.", "bid_deadline": _when(10)}).json()["id"]
    a.put(f"/projects/{pid}/response-requirements", json={"approach": "required", "documents": [{"name": "Method statement", "required": True}], "declarations": [DECL]})
    seen = b.get(f"/projects/{pid}").json()  # B has the draft open
    assert seen["status"] == "draft"
    assert a.post(f"/owner/projects/{pid}/publish").status_code == 200

    # B's page still shows the draft: its save and its upload are refused, not made public amendments.
    r = b.patch(f"/projects/{pid}", json={"title": "Boundary wall v2"}, headers={"If-Match": str(seen["version"])})
    assert r.status_code == 409 and "changed somewhere else" in r.json()["detail"]
    r = b.post(f"/projects/{pid}/drawings", files=[("drawings", ("plan.pdf", b"%PDF-1", "application/pdf"))], headers={"If-Match": str(seen["version"])})
    assert r.status_code == 409
    live = b.get(f"/projects/{pid}").json()
    assert live["title"] == "Boundary wall" and live["material_revision"] == 0
    # Reloaded, B amends it as a published requirement, deliberately.
    r = b.post(f"/projects/{pid}/drawings", files=[("drawings", ("plan.pdf", b"%PDF-1", "application/pdf"))], headers={"If-Match": str(live["version"])})
    assert r.status_code == 200 and r.json()["material_revision"] == 1


def test_an_organisation_whose_founder_left_can_still_be_invited_and_awarded(db):
    owner = _account(db, "owner", "o-founder@example.com")
    founder, member, founder_id, member_id = _organization(db, "service_provider", "Shield W.L.L.", "founder@shield.example", "eng@shield.example")
    profile = db.get(ServiceProviderProfile, founder_id)
    profile.company_name, profile.payment_override_active = "Shield", True
    db.commit()
    _completed(db, owner, member, "First job")
    # The founder hands the representative role on, then leaves.
    assert founder.post(f"/account/organization/representative/{member_id}").status_code == 200
    assert _admin(db).post(f"/admin/users/{founder_id}/deactivate", json={"reason": "left the company"}).status_code == 200

    pid = _tender(owner, title="Second job")
    assert owner.post(f"/owner/projects/{pid}/invitations/{founder_id}").status_code == 204
    _submitted(member, pid)
    owner.post(f"/owner/projects/{pid}/close")
    oid = member.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{oid}/approve").status_code == 200


def _pdf(name):
    return [("files", (name, b"%PDF-1.4 x", "application/pdf"))]


def test_an_answers_files_are_those_its_author_sent_with_it(db):
    a, b, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "a-qa@gulf.example", "b-qa@gulf.example")
    sp = _account(db, "service_provider", "s-qa@example.com")
    other = _account(db, "service_provider", "s-qa-other@example.com")
    pid = _tender(a, title="Boundary wall")
    q = sp.post(f"/projects/{pid}/clarifications", json={"question": "Gate width?"}).json()["id"]
    base = f"/projects/{pid}/clarifications/{q}"
    # B starts an answer with a file; A answers first, with its own file.
    assert b.post(f"{base}/attachments", files=_pdf("b-draft.pdf")).status_code == 200
    assert a.post(f"{base}/attachments", files=_pdf("a-gate.pdf")).status_code == 200
    assert a.post(f"{base}/answer", json={"answer": "4 m."}).status_code == 200
    # B's attempt is refused at both steps; the published answer is A's alone.
    r = b.post(f"{base}/attachments", files=_pdf("b-late.pdf"))
    assert r.status_code == 400 and "already been answered" in r.json()["detail"]
    assert b.post(f"{base}/answer", json={"answer": "3.5 m"}).status_code == 400
    seen = next(c for c in other.get(f"/projects/{pid}/clarifications").json() if c["id"] == q)
    assert [f["file_name"] for f in seen["attachments"] if f["part"] == "answer"] == ["a-gate.pdf"]


def test_an_answered_question_stays_tied_to_the_change_it_brought(db):
    owner = _account(db, "owner", "o-link@example.com")
    sp = _account(db, "service_provider", "s-link@example.com")
    pid = _tender(owner, title="Boundary wall")
    q = sp.post(f"/projects/{pid}/clarifications", json={"question": "Gate width?"}).json()["id"]
    owner.post(f"/projects/{pid}/clarifications/{q}/answer", json={"answer": "4 m"})
    v = owner.get(f"/projects/{pid}").json()["version"]
    r = owner.patch(f"/projects/{pid}", json={"title": "Boundary wall + 4 m gate", "clarification_id": q}, headers={"If-Match": str(v)})
    assert r.status_code == 200
    r = owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(20), "clarification_id": q}, headers={"If-Match": str(r.json()["version"])})
    assert r.status_code == 400 and "already tied" in r.json()["detail"]
    question = next(c for c in sp.get(f"/projects/{pid}/clarifications").json() if c["id"] == q)
    assert question["amendment_number"] == 1


def test_the_deadline_reminder_is_sent_again_before_an_extended_deadline(db, monkeypatch):
    import app.routers.cron as cron_module

    monkeypatch.setattr(cron_module.settings, "cron_secret", "s3cret", raising=False)
    cron = TestClient(app)
    remind = lambda: cron.get("/cron/deadline-reminders", headers={"Authorization": "Bearer s3cret"}).json()["sent"]  # noqa: E731
    owner = _account(db, "owner", "o-remind@example.com")
    pid = _tender(owner, title="Boundary wall")
    project = db.get(Project, pid)
    project.bid_deadline = datetime.utcnow() + timedelta(hours=12)
    db.commit()
    assert remind() == 1

    # Extended, but still within a day: the reminder just sent still holds.
    v = owner.get(f"/projects/{pid}").json()["version"]
    r = owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(0.75)}, headers={"If-Match": str(v)})
    assert r.status_code == 200, r.text
    assert remind() == 0
    # Extended well beyond: a day before the new deadline, the owner is reminded again.
    r = owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(10)}, headers={"If-Match": str(r.json()["version"])})
    assert r.status_code == 200, r.text
    assert remind() == 0
    db.expire_all()
    project = db.get(Project, pid)
    project.bid_deadline = datetime.utcnow() + timedelta(hours=10)  # time passes
    db.commit()
    assert remind() == 1


def _deadline_passes(db, pid, minutes=30):
    project = db.get(Project, pid)
    project.bid_deadline = datetime.utcnow() - timedelta(minutes=minutes)
    db.commit()


def test_close_early_after_the_deadline_is_the_deadlines_own_close(db):
    owner = _account(db, "owner", "o-late-close@example.com")
    sp = _account(db, "service_provider", "s-late-close@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    _deadline_passes(db, pid)  # nothing has read it since
    r = owner.post(f"/owner/projects/{pid}/close")
    assert r.status_code == 400 and "already closed at the deadline" in r.json()["detail"]
    db.expire_all()
    project = db.get(Project, pid)
    assert project.status.value == "closed" and project.closed_at == project.bid_deadline
    assert db.query(AuditLog).filter(AuditLog.action == "project.close", AuditLog.target_id == pid).count() == 0


def test_a_suspended_owner_cant_publish_an_answer(db):
    owner = _account(db, "owner", "o-susp-qa@example.com")
    sp = _account(db, "service_provider", "s-susp-qa@example.com")
    pid = _tender(owner)
    q = sp.post(f"/projects/{pid}/clarifications", json={"question": "Gate width?"}).json()["id"]
    db.get(OwnerProfile, _me(owner)).is_suspended = True
    db.commit()
    r = owner.post(f"/projects/{pid}/clarifications/{q}/answer", json={"answer": "4 m."})
    assert r.status_code == 403
    assert all(c["answer"] is None for c in sp.get(f"/projects/{pid}/clarifications").json())


def test_an_expired_draft_is_refused_the_same_way_everywhere_and_can_start_again(db):
    owner = _account(db, "owner", "o-exp-draft@example.com")
    pid = owner.post("/projects", data={"title": "Boundary wall", "address": "Kaifan", "description": "A wall.", "bid_deadline": _when(10)}).json()["id"]
    v = owner.get(f"/projects/{pid}").json()["version"]
    _deadline_passes(db, pid)  # while its page was open
    expired = "it has expired"
    r = owner.put(f"/projects/{pid}/tender-rules", json={"tender_type": "owner_visible", "questions_allowed": True, "commercial_conditions": {}}, headers={"If-Match": str(v)})
    assert r.status_code == 400 and expired in r.json()["detail"]
    r = owner.post(f"/owner/projects/{pid}/publish")
    assert r.status_code == 400 and expired in r.json()["detail"]
    r = owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(7)}, headers={"If-Match": str(v)})
    assert r.status_code == 400 and expired in r.json()["detail"]
    assert owner.get(f"/projects/{pid}").json()["status"] == "expired"
    assert owner.post(f"/owner/projects/{pid}/restart", json={}).status_code == 201


def test_a_change_cant_move_completion_before_an_open_deliverable(db):
    owner = _account(db, "owner", "o-early-done@example.com")
    sp = _account(db, "service_provider", "s-early-done@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{sp.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    due = kuwait_today() + timedelta(days=25)
    r = owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "Phase 2", "due_date": due.isoformat()}, headers=_v(owner, pid))
    assert r.status_code == 200, r.text
    put_in_force(owner, sp, pid)
    early = (kuwait_today() + timedelta(days=5)).isoformat()
    r = sp.post(f"/projects/{pid}/agreement/variations", json={"description": "Finish early", "completion_date": early}, headers=_v(sp, pid))
    assert r.status_code == 400 and "due after this completion date" in r.json()["detail"]
    # Rescheduling the deliverable in the same change keeps the schedule coherent.
    mid = sp.get(f"/projects/{pid}/agreement").json()["milestones"][0]["id"]
    r = sp.post(f"/projects/{pid}/agreement/variations", json={"description": "Finish early", "completion_date": early,
                                                               "milestone_id": mid, "milestone_due_date": early}, headers=_v(sp, pid))
    assert r.status_code == 200, r.text


def _notices(db, client, kind):
    return db.query(Notification).filter(Notification.user_id == _me(client), Notification.type == kind).all()


def test_the_owner_is_told_when_offers_close_or_nobody_bid(db):
    owner = _account(db, "owner", "o-told@example.com")
    sp = _account(db, "service_provider", "s-told@example.com")
    with_offer, without = _tender(owner, title="Wall"), _tender(owner, title="Gate")
    _submitted(sp, with_offer)
    _deadline_passes(db, with_offer)
    _deadline_passes(db, without)
    owner.get("/owner/projects")  # any read moves them on
    ready = _notices(db, owner, NotificationType.evaluation_ready)
    assert len(ready) == 1 and ready[0].link == f"/owner/projects/{with_offer}" and "1 offer" in ready[0].body
    nobody = _notices(db, owner, NotificationType.requirement_expired)
    assert len(nobody) == 1 and nobody[0].link == f"/owner/projects/{without}"
    owner.get("/owner/projects")
    assert len(_notices(db, owner, NotificationType.evaluation_ready)) == 1  # once


def test_the_owner_is_told_when_a_provider_confirms_its_offer(db):
    owner = _account(db, "owner", "o-confirmed@example.com")
    sp = _account(db, "service_provider", "s-confirmed@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    offer = db.get(Offer, oid)
    offer.proposed_start_date = kuwait_today() - timedelta(days=1)
    db.commit()
    owner.post(f"/owner/projects/{pid}/offers/{oid}/request-confirmation")
    assert sp.post(f"/projects/{pid}/offers/confirm", json={"proposed_start_date": (kuwait_today() + timedelta(days=3)).isoformat()}).status_code == 200
    told = _notices(db, owner, NotificationType.offer_confirmed)
    assert len(told) == 1 and told[0].link == f"/owner/projects/{pid}"

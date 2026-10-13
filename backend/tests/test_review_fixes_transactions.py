"""Review fixes: agreement papers and confirmation, the overdue-review
termination, confirming a suspended offer, Kuwait calendar dates, answers
counted since an offer, post-close withdrawal and the deadline notice."""
from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.agreement import Agreement
from app.models.award_record import AwardRecord
from app.models.clarification import Clarification
from app.models.enums import NotificationType, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.project import Project
from app.routers.agreements import kuwait_today
from app.services.reputation import provider_reputation
from tests.stage7_helpers import put_in_force
from tests.test_batch_a_contract_logic import _awarded, _v
from tests.test_batch_b_tender_fairness import _validity_tender
from tests.test_owner_journey_fixes import _deadline_passes
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender

PDF = {"file": ("signed.pdf", b"%PDF signed", "application/pdf")}


def _late_utc_evening_before_kuwait_today() -> datetime:
    """22:00 UTC yesterday -- already today (01:00) in Kuwait."""
    return datetime.combine(kuwait_today(), time()) - timedelta(hours=2)


# 4 -----------------------------------------------------------------------


def test_a_paper_change_while_preparing_outdates_a_page_holding_the_old_version(db):
    owner, sp, pid, base = _awarded(db, "paperver")
    stale = _v(sp, pid)  # the provider's page, read before the papers changed
    doc = owner.post(f"{base}/documents", data={"kind": "work_order"}, files=PDF)
    assert doc.status_code == 200, doc.text
    r = sp.post(f"{base}/confirm", headers=stale)
    assert r.status_code == 409  # terms now include a paper that page never showed
    stale = _v(sp, pid)
    assert owner.delete(f"{base}/documents/{doc.json()['documents'][0]['id']}").status_code == 200
    assert sp.post(f"{base}/confirm", headers=stale).status_code == 409  # nor one that omits it


def test_the_provider_is_told_when_a_paper_change_clears_its_confirmation(db):
    owner, sp, pid, base = _awarded(db, "papertell")
    assert owner.patch(base, json={"effective_date": kuwait_today().isoformat()}, headers=_v(owner, pid)).status_code == 200
    assert sp.post(f"{base}/confirm", headers=_v(sp, pid)).status_code == 200
    me = sp.get("/auth/me").json()["id"]

    def told():
        return db.query(Notification).filter(Notification.user_id == me, Notification.type == NotificationType.tender_amendment).count()

    before = told()
    assert owner.post(f"{base}/documents", data={"kind": "work_order"}, files=PDF).json()["provider_confirmed_at"] is None
    assert told() == before + 1
    note = db.query(Notification).filter(Notification.user_id == me, Notification.type == NotificationType.tender_amendment).order_by(Notification.created_at.desc()).first()
    assert note.link == f"/service-provider/projects/{pid}/offer" and "confirm the terms again" in note.body



def test_the_provider_is_told_when_any_owner_change_clears_its_confirmation(db):
    """Not only papers: the date, the reference and the deliverables too."""
    owner, sp, pid, base = _awarded(db, "termstell")
    assert owner.patch(base, json={"effective_date": kuwait_today().isoformat()}, headers=_v(owner, pid)).status_code == 200
    me = sp.get("/auth/me").json()["id"]

    def unread():
        return db.query(Notification).filter(Notification.user_id == me, Notification.type == NotificationType.tender_amendment,
                                             Notification.is_read.is_(False)).count()

    def confirm_and_clear_inbox():
        assert sp.post(f"{base}/confirm", headers=_v(sp, pid)).status_code == 200
        db.query(Notification).filter(Notification.user_id == me).update({Notification.is_read: True})
        db.commit()

    confirm_and_clear_inbox()
    r = owner.patch(base, json={"reference": "PO-77"}, headers=_v(owner, pid))
    assert r.status_code == 200 and r.json()["provider_confirmed_at"] is None and unread() == 1
    confirm_and_clear_inbox()
    r = owner.post(f"{base}/milestones", json={"title": "Panels"}, headers=_v(owner, pid))
    assert r.status_code == 200 and r.json()["provider_confirmed_at"] is None and unread() == 1
    # A change before any confirmation tells nobody -- there was nothing to clear.
    db.query(Notification).filter(Notification.user_id == me).update({Notification.is_read: True})
    db.commit()
    assert owner.patch(base, json={"reference": "PO-78"}, headers=_v(owner, pid)).status_code == 200 and unread() == 0

# 5 -----------------------------------------------------------------------


def _submitted_overdue(db, tag):
    owner, sp, pid, base = _awarded(db, tag)
    put_in_force(owner, sp, pid)
    assert sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid)).status_code == 200
    assert sp.post(f"{base}/completion/submit", json={}, headers=_v(sp, pid)).status_code == 200
    agreement = db.query(Agreement).filter_by(project_id=pid).one()
    agreement.completion_submitted_at = datetime.utcnow() - timedelta(days=31)
    db.commit()
    return owner, sp, pid, base


def test_the_silent_owner_cannot_terminate_once_the_review_is_overdue(db):
    owner, sp, pid, base = _submitted_overdue(db, "silentowner")
    assert owner.get(base).json()["completion_review_overdue"] is True
    r = owner.post(f"{base}/terminate", json={"reason": "Changed my mind."}, headers=_v(owner, pid))
    assert r.status_code == 409 and "service provider may terminate" in r.json()["detail"]


def test_the_overdue_termination_does_not_count_against_the_provider(db):
    owner, sp, pid, base = _submitted_overdue(db, "overduerep")
    r = sp.post(f"{base}/terminate", json={"reason": "No answer for 30 days."}, headers=_v(sp, pid))
    assert r.status_code == 200 and r.json()["status"] == "terminated", r.text
    provider_id = db.query(AwardRecord).filter_by(project_id=pid).one().service_provider_id
    assert provider_reputation(db, provider_id).terminated_transactions == 0
    # A termination of started work that wasn't awaiting review still counts.
    owner2, sp2, pid2, base2 = _awarded(db, "overduerep2")
    put_in_force(owner2, sp2, pid2)
    assert sp2.post(f"{base2}/start-work", json={}, headers=_v(sp2, pid2)).status_code == 200
    assert owner2.post(f"{base2}/terminate", json={"reason": "Too slow."}, headers=_v(owner2, pid2)).status_code == 200
    provider2 = db.query(AwardRecord).filter_by(project_id=pid2).one().service_provider_id
    assert provider_reputation(db, provider2).terminated_transactions == 1


# 6 -----------------------------------------------------------------------


def test_a_suspended_offer_cannot_be_confirmed_after_the_close(db):
    owner = _account(db, "owner", "o-suspconfirm@example.com")
    sp = _account(db, "service_provider", "s-suspconfirm@example.com")
    pid = _validity_tender(owner, days=10)
    _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    offer = db.get(Offer, sp.get(f"/projects/{pid}/offers/mine").json()["id"])
    project = db.get(Project, pid)
    project.closed_at = datetime.utcnow() - timedelta(days=11)  # validity lapsed: confirming would restart it
    offer.is_suspended = True
    db.commit()
    r = sp.post(f"/projects/{pid}/offers/confirm")
    assert r.status_code == 400 and "suspended" in r.json()["detail"]
    db.refresh(offer)
    assert offer.validity_confirmed_at is None


# 9 -----------------------------------------------------------------------


def _award_late_utc_evening(db, pid):
    award = db.query(AwardRecord).filter_by(project_id=pid).one()
    award.created_at = _late_utc_evening_before_kuwait_today()
    db.commit()


def test_a_deliverable_cannot_be_due_before_the_award_day_in_kuwait(db):
    owner, sp, pid, base = _awarded(db, "msdate")
    _award_late_utc_evening(db, pid)
    yesterday = (kuwait_today() - timedelta(days=1)).isoformat()  # the award's UTC date, not Kuwait's
    r = owner.post(f"{base}/milestones", json={"title": "Slab", "due_date": yesterday}, headers=_v(owner, pid))
    assert r.status_code == 400 and "before the award" in r.json()["detail"]


def test_a_variation_date_cannot_be_before_the_award_day_in_kuwait(db):
    owner, sp, pid, base = _awarded(db, "vardate")
    put_in_force(owner, sp, pid)
    _award_late_utc_evening(db, pid)
    yesterday = (kuwait_today() - timedelta(days=1)).isoformat()
    r = sp.post(f"{base}/variations", json={"description": "Later finish", "completion_date": yesterday}, headers=_v(sp, pid))
    assert r.status_code == 400 and "before the award" in r.json()["detail"]


def test_the_response_deadline_is_read_on_kuwaits_calendar():
    from app.routers.projects import _check_execution_timing
    from app.services.offer_response import check_commitment, timing_conflicts

    deadline = _late_utc_evening_before_kuwait_today()  # closes today in Kuwait
    utc_day = deadline.date()
    project = SimpleNamespace(bid_deadline=deadline, expected_start_date=None, expected_completion_date=None, expected_duration_days=None)
    with pytest.raises(HTTPException):
        check_commitment(project, utc_day, None, 10)
    with pytest.raises(HTTPException):
        _check_execution_timing(deadline, utc_day, None, 10)
    offer = SimpleNamespace(proposed_start_date=utc_day, proposed_completion_date=None, proposed_duration_days=10)
    assert "before_close" in timing_conflicts(project, offer)
    check_commitment(project, kuwait_today(), None, 10)  # the Kuwait day itself is fine


# 10 ----------------------------------------------------------------------


def test_an_answer_to_an_earlier_private_question_counts_for_every_provider(db):
    owner = _account(db, "owner", "o-privall@example.com")
    sp = _account(db, "service_provider", "s-privall@example.com")
    asker = _account(db, "service_provider", "a-privall@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    _submitted(asker, pid)
    q = asker.post(f"/projects/{pid}/clarifications", json={"question": "Is the parapet included?"}).json()
    row = db.get(Clarification, q["id"])
    row.shared_with_all = False  # asked privately before every answer was shared
    db.commit()
    assert owner.post(f"/projects/{pid}/clarifications/{q['id']}/answer", json={"answer": "Yes."}).status_code == 200
    # The answer is published to the whole field ...
    assert any(c["answer"] == "Yes." for c in sp.get(f"/projects/{pid}/clarifications").json())
    # ... so it counts for every provider's offer, not only the asker's.
    assert sp.get(f"/projects/{pid}/offers/mine").json()["answers_since"] == 1
    assert asker.get(f"/projects/{pid}/offers/mine").json()["answers_since"] == 1


# 11 ----------------------------------------------------------------------


def test_an_offer_whose_start_passed_can_be_withdrawn_after_the_close(db):
    owner = _account(db, "owner", "o-startwd@example.com")
    sp = _account(db, "service_provider", "s-startwd@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    offer = db.get(Offer, sp.get(f"/projects/{pid}/offers/mine").json()["id"])
    offer.proposed_start_date = kuwait_today() - timedelta(days=2)
    db.commit()
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert mine["start_passed"] is True and not mine.get("validity_lapsed")  # the UI offers Withdraw
    r = sp.post(f"/projects/{pid}/offers/withdraw")
    assert r.status_code == 200 and r.json()["status"] == "withdrawn", r.text


def test_an_offer_standing_as_made_still_cannot_be_withdrawn_after_the_close(db):
    owner = _account(db, "owner", "o-standwd@example.com")
    sp = _account(db, "service_provider", "s-standwd@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 400


# 12 ----------------------------------------------------------------------


def test_a_requirement_closed_on_a_suspended_offer_is_never_reported_with_none(db):
    owner = _account(db, "owner", "o-suspclose@example.com")
    sp = _account(db, "service_provider", "s-suspclose@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    offer = db.get(Offer, sp.get(f"/projects/{pid}/offers/mine").json()["id"])
    offer.is_suspended = True
    db.commit()
    _deadline_passes(db, pid)
    owner.get("/owner/projects")  # any read moves it on
    assert db.get(Project, pid).status == ProjectStatus.closed
    me = owner.get("/auth/me").json()["id"]
    ready = db.query(Notification).filter(Notification.user_id == me, Notification.type == NotificationType.evaluation_ready).all()
    # PR #22 review: the owner can't see a suspended offer, so it is neither
    # counted nor reported as 0 -- the notice says the offers are under review.
    assert len(ready) == 1 and "0 offer" not in ready[0].body and "1 offer" not in ready[0].body and "under review" in ready[0].body

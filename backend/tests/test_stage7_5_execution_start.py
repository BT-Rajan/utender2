"""Stage 7.5: execution start. On the award's agreement: when the work
actually started (server time, recorded once by either party), against the
planned start the winner committed to; the status (not started / in progress /
terminated) is derived, never stored; the other party is told; nobody else
sees or touches it; nothing about the award or the requirement moves."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import NotificationType, OfferStatus, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.project import Project
from app.routers import agreements as agreements_router
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _d, _submitted, _tender
from tests.test_stage3_bid_integrity import needs_mysql


def _relogin(email):
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _awarded(db):
    owner = _account(db, "owner", "owner@example.com", organization="Gulf Holdings W.L.L.")
    a, b = _account(db, "service_provider", "amal@example.com"), _account(db, "service_provider", "badr@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    wid = a.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    return owner, a, b, pid, wid


def _v(client, pid):
    return {"If-Match": str(client.get(f"/projects/{pid}/agreement").json()["version"])}


def test_the_winner_starts_the_work_and_both_see_the_same(db):
    owner, a, b, pid, wid = _awarded(db)
    award_before = db.query(AwardRecord).one().amount
    before = a.get(f"/projects/{pid}/agreement").json()
    assert (before["execution_status"], before["work_started_at"]) == ("not_started", None)
    assert (before["planned_start_date"], before["planned_start_source"]) == (_d(20), "offer")  # the winner's own commitment

    t0 = datetime.utcnow().replace(microsecond=0)
    r = a.post(f"/projects/{pid}/agreement/start-work", json={"note": " Mobilised to site. "}, headers=_v(a, pid))
    assert r.status_code == 200, r.text
    started = r.json()
    assert (started["execution_status"], started["work_started_party"], started["work_start_note"], started["work_started_by_name"]) == ("in_progress", "provider", "Mobilised to site.", "N")
    stamp = datetime.fromisoformat(started["work_started_at"].rstrip("Z"))
    assert t0 - timedelta(seconds=2) <= stamp <= datetime.utcnow() + timedelta(seconds=2)  # the server's clock

    for client in (owner, _relogin("owner@example.com"), _admin(db)):
        seen = client.get(f"/projects/{pid}/agreement").json()
        assert (seen["execution_status"], seen["work_started_at"], seen["work_started_party"]) == ("in_progress", started["work_started_at"], "provider")
    assert owner.get(f"/projects/{pid}/agreement").json()["work_started_by_name"] is None  # the other side sees the side, not the member
    assert owner.get(f"/projects/{pid}").json()["status"] == "awarded"  # the requirement's lifecycle is untouched

    # The owner side is told, once, with a link to its own requirement.
    owner_id = owner.get("/auth/me").json()["id"]
    (note,) = db.query(Notification).filter(Notification.user_id == owner_id, Notification.type == NotificationType.work_started).all()
    assert note.link == f"/owner/projects/{pid}"
    assert db.query(Notification).filter(Notification.type == NotificationType.work_started).count() == 1
    (entry,) = db.query(AuditLog).filter(AuditLog.action == "agreement.start_work").all()
    assert (entry.previous_value, entry.new_value, entry.target_id) == ("not_started", "in_progress", started["id"])

    db.expire_all()
    assert (db.get(Project, pid).status, db.get(Offer, wid).status, db.query(AwardRecord).one().amount) == (ProjectStatus.awarded, OfferStatus.approved, award_before)


def test_the_owner_may_record_it_and_the_winner_is_told(db):
    owner, a, b, pid, wid = _awarded(db)
    assert owner.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(owner, pid)).json()["work_started_party"] == "owner"
    a_id = a.get("/auth/me").json()["id"]
    (note,) = db.query(Notification).filter(Notification.user_id == a_id, Notification.type == NotificationType.work_started).all()
    assert note.link == f"/service-provider/projects/{pid}/offer"
    b_id = b.get("/auth/me").json()["id"]
    assert db.query(Notification).filter(Notification.user_id == b_id, Notification.type == NotificationType.work_started).count() == 0


def test_nobody_else_sees_or_starts_it(db):
    owner, a, b, pid, wid = _awarded(db)
    others = (b, _account(db, "service_provider", "rival@example.com", organization="Rival Contracting"), _account(db, "owner", "other@example.com", organization="Other Co"))
    for client in others:
        assert client.get(f"/projects/{pid}/agreement").status_code == 404
        assert client.post(f"/projects/{pid}/agreement/start-work", json={}).status_code == 404
    assert TestClient(app).post(f"/projects/{pid}/agreement/start-work", json={}).status_code == 401
    assert _admin(db).post(f"/projects/{pid}/agreement/start-work", json={}).status_code == 403  # admins read only
    other_pid = _tender(owner)  # the owner's own requirement that was never awarded
    assert owner.post(f"/projects/{other_pid}/agreement/start-work", json={}).status_code == 404
    assert a.post(f"/projects/{other_pid}/agreement/start-work", json={}).status_code == 404
    assert db.get(Agreement, db.query(Agreement).one().id).work_started_at is None


def test_repeats_stale_tabs_and_endings(db):
    owner, a, b, pid, wid = _awarded(db)
    stale = _v(owner, pid)
    owner.patch(f"/projects/{pid}/agreement", json={"reference": "PO-1"}, headers=stale)  # another tab moved it on
    assert a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=stale).status_code == 409
    fresh = _v(a, pid)
    assert a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=fresh).status_code == 200
    assert a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=fresh).status_code == 400  # double-click
    assert owner.post(f"/projects/{pid}/agreement/start-work", json={}).status_code == 400  # the other party, after
    first = db.query(Agreement).one()
    db.refresh(first)
    # Terminated after starting: the start stays on record, it can't be restarted.
    assert owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid)).status_code == 200
    after = a.get(f"/projects/{pid}/agreement").json()
    assert (after["execution_status"], after["work_started_party"]) == ("terminated", "provider")
    assert a.post(f"/projects/{pid}/agreement/start-work", json={}).status_code == 400
    assert db.query(AuditLog).filter(AuditLog.action == "agreement.start_work").count() == 1


def test_a_terminated_agreement_or_no_award_cannot_start(db):
    owner, a, b, pid, wid = _awarded(db)
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Did not proceed."}, headers=_v(owner, pid))
    assert a.post(f"/projects/{pid}/agreement/start-work", json={}).status_code == 400
    assert a.get(f"/projects/{pid}/agreement").json()["execution_status"] == "terminated"

    pid2 = _tender(owner, title="Second")
    _submitted(a, pid2)
    assert a.post(f"/projects/{pid2}/agreement/start-work", json={}).status_code == 404  # open: no award
    owner.post(f"/owner/projects/{pid2}/close")
    owner.post(f"/owner/projects/{pid2}/cancel", json={"reason": "other"})
    assert a.post(f"/projects/{pid2}/agreement/start-work", json={}).status_code == 404  # cancelled


def test_a_failed_notification_never_undoes_the_start(db, monkeypatch):
    owner, a, b, pid, wid = _awarded(db)

    def broken(*args, **kwargs):
        raise RuntimeError("mail server down")

    monkeypatch.setattr(agreements_router, "notify_team", broken)
    r = a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid))
    assert r.status_code == 200 and r.json()["execution_status"] == "in_progress"
    db.expire_all()
    assert db.query(Agreement).one().work_started_at is not None


def test_a_failed_save_records_nothing(db, monkeypatch):
    owner, a, b, pid, wid = _awarded(db)

    def failing_log(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(agreements_router, "log_action", failing_log)
    with pytest.raises(RuntimeError):
        a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid))
    monkeypatch.undo()
    db.expire_all()
    assert db.query(Agreement).one().work_started_at is None
    assert a.get(f"/projects/{pid}/agreement").json()["execution_status"] == "not_started"


def test_planned_start_falls_back_to_the_requirement(db):
    owner, a, b, pid, wid = _awarded(db)
    offer = db.get(Offer, wid)
    offer.proposed_start_date = None
    db.get(Project, pid).expected_start_date = datetime.utcnow().date() + timedelta(days=30)
    db.commit()
    seen = owner.get(f"/projects/{pid}/agreement").json()
    assert seen["planned_start_source"] == "requirement"


@needs_mysql
def test_owner_and_winner_starting_at_once_is_one_start(db):
    owner, a, b, pid, wid = _awarded(db)
    clients = [_relogin("owner@example.com"), _relogin("amal@example.com"), _relogin("owner@example.com"), _relogin("amal@example.com")]
    with ThreadPoolExecutor(4) as pool:
        codes = sorted(r.status_code for r in pool.map(lambda c: c.post(f"/projects/{pid}/agreement/start-work", json={}), clients))
    assert codes == [200, 400, 400, 400], codes
    assert db.query(AuditLog).filter(AuditLog.action == "agreement.start_work").count() == 1
    assert db.query(Notification).filter(Notification.type == NotificationType.work_started).count() == 1


@needs_mysql
def test_start_against_termination_settles_on_one_story(db):
    owner, a, b, pid, wid = _awarded(db)
    calls = [
        lambda: _relogin("amal@example.com").post(f"/projects/{pid}/agreement/start-work", json={}),
        lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}),
    ]
    with ThreadPoolExecutor(2) as pool:
        start, end = [f.result() for f in [pool.submit(c) for c in calls]]
    assert end.status_code == 200  # termination is allowed either way
    final = owner.get(f"/projects/{pid}/agreement").json()
    assert final["execution_status"] == "terminated"
    assert (start.status_code == 200) == (final["work_started_at"] is not None)

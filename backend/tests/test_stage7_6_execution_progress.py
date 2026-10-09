"""Stage 7.6: execution progress. Once the work has started, either party
records short progress notes, puts the work on hold or resumes it; both read
the same status and the same history; the other party is told of a hold or a
resumption; nothing about the award, the winning offer or the requirement
moves; nobody else sees or touches any of it."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement, AgreementDocument, ExecutionUpdate
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import NotificationType, OfferStatus, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.project import Project
from app.routers import agreements as agreements_router
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _submitted, _tender
from tests.stage7_helpers import put_in_force


def _relogin(email):
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _v(client, pid):
    return {"If-Match": str(client.get(f"/projects/{pid}/agreement").json()["version"])}


def _progress(client, pid, action, note=None, headers=None):
    return client.post(f"/projects/{pid}/agreement/progress", json={"action": action, "note": note}, headers=_v(client, pid) if headers is None else headers)


def _started(db, start=True):
    owner = _account(db, "owner", "owner@example.com", organization="Gulf Holdings W.L.L.")
    a, b = _account(db, "service_provider", "amal@example.com"), _account(db, "service_provider", "badr@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    wid = a.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    put_in_force(owner, a, pid)  # Batch A: the work is done only under an agreement in force
    if start:
        assert a.post(f"/projects/{pid}/agreement/start-work", json={"note": "On site."}, headers=_v(a, pid)).status_code == 200
    return owner, a, b, pid, wid


def _notes(db, client, kind=NotificationType.execution_updated):
    uid = client.get("/auth/me").json()["id"]
    return db.query(Notification).filter(Notification.user_id == uid, Notification.type == kind).all()


def test_progress_hold_and_resume_seen_alike_by_both(db):
    owner, a, b, pid, wid = _started(db)
    award = db.query(AwardRecord).one()
    before = (award.amount, award.offer_id, award.offer_revision)
    doc = a.post(f"/projects/{pid}/agreement/documents", data={"kind": "work_order"}, files={"file": ("wo.pdf", b"%PDF wo", "application/pdf")}).json()["documents"][0]["id"]

    r = _progress(a, pid, "update", "  Foundations poured. ")
    assert r.status_code == 200 and r.json()["execution_status"] == "in_progress"
    r = _progress(a, pid, "hold", "Waiting for permit.")
    assert r.status_code == 200 and (r.json()["execution_status"], r.json()["on_hold_since"].endswith("Z")) == ("on_hold", True)
    for client in (owner, _relogin("owner@example.com"), _admin(db)):
        seen = client.get(f"/projects/{pid}/agreement").json()
        assert seen["execution_status"] == "on_hold"
        assert [(h["kind"], h["party"], h["note"]) for h in seen["execution_history"]] == [
            ("started", "provider", "On site."), ("progress", "provider", "Foundations poured."), ("on_hold", "provider", "Waiting for permit."),
        ]
        sequences = [h["sequence"] for h in seen["execution_history"]]
        assert sequences == sorted(sequences)  # numbered in the order they happened
    # On hold: everything else stands -- documents open, notes can still be added.
    assert owner.get(f"/projects/{pid}/agreement/documents/{doc}/file", follow_redirects=False).status_code == 303
    assert _progress(owner, pid, "update", "Permit applied for.").json()["execution_status"] == "on_hold"

    r = _progress(owner, pid, "resume")
    assert r.status_code == 200 and (r.json()["execution_status"], r.json()["on_hold_since"]) == ("in_progress", None)
    history = a.get(f"/projects/{pid}/agreement").json()["execution_history"]
    assert [h["kind"] for h in history] == ["started", "progress", "on_hold", "progress", "resumed"]
    # Names: one's own side's members; the other party sees the side.
    assert [h["recorded_by_name"] for h in history] == ["N", "N", "N", None, None]

    # The other party was told of the hold (owner side) and of the resumption (winner side) -- and only of those.
    assert [n.link for n in _notes(db, owner)] == [f"/owner/projects/{pid}"]
    assert [n.link for n in _notes(db, a)] == [f"/service-provider/projects/{pid}/offer"]
    assert _notes(db, b) == []
    actions = [e.action for e in db.query(AuditLog).filter(AuditLog.action.like("agreement.execution_%"))]
    assert sorted(actions) == sorted(["agreement.execution_progress", "agreement.execution_on_hold", "agreement.execution_progress", "agreement.execution_resumed"])

    db.expire_all()
    award = db.query(AwardRecord).one()
    assert (award.amount, award.offer_id, award.offer_revision) == before
    assert (db.get(Project, pid).status, db.get(Offer, wid).status) == (ProjectStatus.awarded, OfferStatus.approved)
    assert db.query(AgreementDocument).count() == 1 and db.query(Agreement).one().status == "active"  # Batch A: in force (put there before the start)


def test_nobody_else_sees_or_moves_it(db):
    owner, a, b, pid, wid = _started(db)
    others = (b, _account(db, "service_provider", "rival@example.com", organization="Rival Contracting"), _account(db, "owner", "other@example.com", organization="Other Co"))
    for client in others:
        assert client.get(f"/projects/{pid}/agreement").status_code == 404
        assert client.post(f"/projects/{pid}/agreement/progress", json={"action": "hold"}).status_code == 404
    assert TestClient(app).post(f"/projects/{pid}/agreement/progress", json={"action": "hold"}).status_code == 401
    assert _admin(db).post(f"/projects/{pid}/agreement/progress", json={"action": "hold"}).status_code == 403
    other = _tender(owner, title="Never awarded")
    assert owner.post(f"/projects/{other}/agreement/progress", json={"action": "update", "note": "x"}).status_code == 404
    # Batch A: the confirmation and the putting in force are on the history too.
    assert [u.kind for u in db.query(ExecutionUpdate).order_by(ExecutionUpdate.sequence)] == ["terms_confirmed", "in_force", "started"]  # just the start


def test_invalid_transitions_are_refused(db):
    owner, a, b, pid, wid = _started(db, start=False)
    for action, note in (("update", "Early claim."), ("hold", None), ("resume", None)):
        assert _progress(a, pid, action, note).status_code == 400  # not started: no progress to claim
    a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid))
    assert _progress(a, pid, "update", "   ").status_code == 400  # a note says something
    assert _progress(a, pid, "resume").status_code == 400  # not on hold
    assert _progress(a, pid, "hold").status_code == 200
    assert _progress(owner, pid, "hold").status_code == 400  # already on hold
    # Terminated while on hold: nothing resumes or progresses it again.
    assert owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Abandoned."}, headers=_v(owner, pid)).status_code == 200
    seen = a.get(f"/projects/{pid}/agreement").json()
    assert (seen["execution_status"], seen["on_hold_since"]) == ("terminated", None)
    for action, note in (("resume", None), ("update", "Back on site."), ("hold", None)):
        assert _progress(a, pid, action, note).status_code == 400
    assert [h["kind"] for h in seen["execution_history"]] == ["started", "on_hold"]  # history kept


def test_cancelled_or_unawarded_requirements_have_no_progress(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    assert _progress(a, pid, "update", "x", headers={}).status_code == 404
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "other"})
    assert _progress(a, pid, "update", "x", headers={}).status_code == 404
    assert db.query(ExecutionUpdate).count() == 0


def test_stale_tabs_double_clicks_and_failures(db, monkeypatch):
    owner, a, b, pid, wid = _started(db)
    stale = _v(owner, pid)
    assert _progress(a, pid, "hold").status_code == 200
    assert _progress(owner, pid, "hold", headers=stale).status_code == 400  # the state answers first: already on hold
    assert _progress(owner, pid, "update", "Seen on site.", headers=stale).status_code == 409  # the page from before the hold
    fresh = _v(owner, pid)
    assert _progress(owner, pid, "resume", headers=fresh).status_code == 200
    assert _progress(owner, pid, "resume", headers=fresh).status_code == 400  # the double-click: no longer on hold
    assert _progress(owner, pid, "resume").status_code == 400  # a plain retry

    def broken(*args, **kwargs):
        raise RuntimeError("mail server down")

    monkeypatch.setattr(agreements_router, "notify_team", broken)
    assert _progress(a, pid, "hold").json()["execution_status"] == "on_hold"  # stands without its notification
    monkeypatch.undo()

    def failing_log(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(agreements_router, "log_action", failing_log)
    with pytest.raises(RuntimeError):
        _progress(a, pid, "resume")
    monkeypatch.undo()
    db.expire_all()
    assert a.get(f"/projects/{pid}/agreement").json()["execution_status"] == "on_hold"  # nothing half-applied
    assert [u.kind for u in db.query(ExecutionUpdate).order_by(ExecutionUpdate.sequence)] == ["terms_confirmed", "in_force", "started", "on_hold", "resumed", "on_hold"]  # Batch A: confirmation and in-force recorded first


@needs_mysql
def test_simultaneous_hold_and_resume_settle_consistently(db):
    owner, a, b, pid, wid = _started(db)
    clients = [_relogin("owner@example.com"), _relogin("amal@example.com"), _relogin("owner@example.com"), _relogin("amal@example.com")]
    with ThreadPoolExecutor(4) as pool:
        codes = sorted(r.status_code for r in pool.map(lambda c: c.post(f"/projects/{pid}/agreement/progress", json={"action": "hold"}), clients))
    assert codes == [200, 400, 400, 400], codes
    # Hold and resume at once, many times: the history numbering never collides and always matches the state.
    for _ in range(3):
        pair = [lambda: _relogin("amal@example.com").post(f"/projects/{pid}/agreement/progress", json={"action": "resume"}),
                lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/progress", json={"action": "update", "note": "Checked."})]
        with ThreadPoolExecutor(2) as pool:
            [f.result() for f in [pool.submit(c) for c in pair]]
        _relogin("owner@example.com").post(f"/projects/{pid}/agreement/progress", json={"action": "hold"})
    db.expire_all()
    rows = db.query(ExecutionUpdate).order_by(ExecutionUpdate.sequence).all()
    assert [r.sequence for r in rows] == list(range(1, len(rows) + 1))
    holds = [r.kind for r in rows if r.kind in ("on_hold", "resumed")]
    assert all(x != y for x, y in zip(holds, holds[1:]))  # never two holds or two resumptions in a row
    assert (db.query(Agreement).one().on_hold_at is not None) == (holds[-1] == "on_hold")


@needs_mysql
def test_resume_against_termination_is_one_story(db):
    owner, a, b, pid, wid = _started(db)
    _progress(a, pid, "hold")
    calls = [lambda: _relogin("amal@example.com").post(f"/projects/{pid}/agreement/progress", json={"action": "resume"}),
             lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."})]
    with ThreadPoolExecutor(2) as pool:
        resume, end = [f.result() for f in [pool.submit(c) for c in calls]]
    assert end.status_code == 200
    final = owner.get(f"/projects/{pid}/agreement").json()
    assert final["execution_status"] == "terminated"
    assert ([h["kind"] for h in final["execution_history"]][-1] == "resumed") == (resume.status_code == 200)

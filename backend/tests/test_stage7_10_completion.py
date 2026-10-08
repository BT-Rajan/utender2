"""Stage 7.10: owner acceptance of the work. Deliverables are delivered and
accepted one by one (7.7); the whole work is submitted as complete by the
winner only once every deliverable is accepted, and the owner side accepts it
or returns it for correction. Submitted is not accepted; accepted is not
closed. Nothing reopens or contradicts accepted work."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement, ExecutionUpdate
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import NotificationType, OfferStatus, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.project import Project
from app.routers import completion as completion_router
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _d, _submitted, _tender

REPORT = ("completion-report.pdf", b"%PDF completion", "application/pdf")


def _relogin(email):
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _a(client, pid):
    return client.get(f"/projects/{pid}/agreement").json()


def _v(client, pid):
    return {"If-Match": str(_a(client, pid)["version"])}


def _do(client, pid, verb, note=None, headers=None):
    return client.post(f"/projects/{pid}/agreement/completion/{verb}", json={"note": note}, headers=_v(client, pid) if headers is None else headers)


def _started(db, milestones=()):
    owner = _account(db, "owner", "owner@example.com", organization="Gulf Holdings W.L.L.")
    a, b = _account(db, "service_provider", "amal@example.com"), _account(db, "service_provider", "badr@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    wid = a.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    ids = []
    for title in milestones:
        r = owner.post(f"/projects/{pid}/agreement/milestones", json={"title": title}, headers=_v(owner, pid))
        ids.append(r.json()["milestones"][-1]["id"])
    owner.patch(f"/projects/{pid}/agreement", json={"effective_date": _d(1)}, headers=_v(owner, pid))
    owner.post(f"/projects/{pid}/agreement/activate", headers=_v(owner, pid))
    assert a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid)).status_code == 200
    return owner, a, b, pid, wid, ids


def _milestone(client, pid, mid, verb, note=None):
    m = next(x for x in _a(client, pid)["milestones"] if x["id"] == mid)
    return client.post(f"/projects/{pid}/agreement/milestones/{mid}/{verb}", json={"note": note}, headers={"If-Match": str(m["version"])})


def test_simple_work_submitted_returned_resubmitted_accepted(db):
    owner, a, b, pid, wid, _ = _started(db)
    assert _do(owner, pid, "accept").status_code in (400, 403)  # nothing submitted, and the owner can't submit
    assert _do(owner, pid, "submit").status_code == 403
    r = _do(a, pid, "submit", "All works finished; snag list cleared.")
    assert r.status_code == 200 and (r.json()["completion_status"], r.json()["execution_status"]) == ("submitted", "in_progress")
    submission = r.json()["execution_history"][-1]["id"]
    assert a.post(f"/projects/{pid}/agreement/documents", data={"kind": "completion_report", "execution_update_id": submission}, files={"file": REPORT}).status_code == 200
    assert _do(a, pid, "accept").status_code == 403  # never its own acceptance

    assert _do(owner, pid, "return").status_code == 400  # a return says what to correct
    r = _do(owner, pid, "return", "Paint touch-ups on level 2.")
    assert r.json()["completion_status"] == "returned"
    seen = _a(a, pid)
    assert (seen["completion_status"], seen["completion_decision_note"]) == ("returned", "Paint touch-ups on level 2.")
    assert _do(a, pid, "submit", "Touch-ups done.").json()["completion_status"] == "submitted"
    r = _do(owner, pid, "accept", "Accepted.")
    assert r.status_code == 200
    for client in (owner, a, _admin(db)):
        seen = _a(client, pid)
        assert (seen["completion_status"], seen["execution_status"], seen["completion_decided_at"].endswith("Z")) == ("accepted", "accepted", True)
        whole = [(h["kind"], h["party"]) for h in seen["execution_history"] if h["milestone_id"] is None and h["kind"] in ("delivered", "accepted", "returned")]
        assert whole == [("delivered", "provider"), ("returned", "owner"), ("delivered", "provider"), ("accepted", "owner")]
        assert any(d["execution_update_id"] == submission for d in seen["documents"])  # the evidence stays on the first submission

    actions = sorted(e.action for e in db.query(AuditLog).filter(AuditLog.action.like("completion.%")))
    assert actions == ["completion.accept", "completion.return", "completion.submit", "completion.submit"]
    links = {n.link for n in db.query(Notification).filter(Notification.type == NotificationType.execution_updated)}
    assert links == {f"/owner/projects/{pid}", f"/service-provider/projects/{pid}/offer"}
    b_id = b.get("/auth/me").json()["id"]
    assert db.query(Notification).filter(Notification.user_id == b_id).filter(Notification.type == NotificationType.execution_updated).count() == 0
    db.expire_all()
    assert (db.get(Project, pid).status, db.get(Offer, wid).status, db.query(AwardRecord).one().amount) == (ProjectStatus.awarded, OfferStatus.approved, 1000)
    assert db.query(Agreement).one().status == "active"  # accepted, not yet closed (Stage 7.11)


def test_deliverables_gate_the_whole_work(db):
    owner, a, b, pid, wid, (m1, m2) = _started(db, milestones=("Panels", "Report"))
    _milestone(a, pid, m1, "deliver")
    _milestone(owner, pid, m1, "accept")
    seen = _a(owner, pid)
    assert (seen["outstanding_deliverables"], seen["completion_status"]) == (1, None)  # one accepted, one pending: not complete
    r = _do(a, pid, "submit")
    assert r.status_code == 400 and "Every deliverable" in r.json()["detail"]
    _milestone(a, pid, m2, "deliver")
    _milestone(owner, pid, m2, "return", "Missing appendix.")
    assert _do(a, pid, "submit").status_code == 400  # returned is not accepted
    _milestone(a, pid, m2, "deliver")
    _milestone(owner, pid, m2, "accept")
    assert _a(a, pid)["outstanding_deliverables"] == 0
    assert _do(a, pid, "submit").status_code == 200


def test_accepted_work_cannot_be_contradicted(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    # While awaiting review: no hold, no change to the agreed work.
    assert a.post(f"/projects/{pid}/agreement/progress", json={"action": "hold"}, headers=_v(a, pid)).status_code == 409
    assert owner.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra"}, headers=_v(owner, pid)).status_code == 409
    _do(owner, pid, "accept")
    for r in (
        a.post(f"/projects/{pid}/agreement/progress", json={"action": "update", "note": "More"}, headers=_v(a, pid)),
        owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "x"}, headers=_v(owner, pid)),
        owner.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra"}, headers=_v(owner, pid)),
        _do(a, pid, "submit"),
        _do(owner, pid, "return", "Changed my mind."),
    ):
        assert r.status_code == 409, r.text
        assert "This page now shows the latest." in r.json()["detail"]
    assert _a(owner, pid)["completion_status"] == "accepted"


def test_preconditions_and_terminal_states(db):
    owner, a, b, pid, wid, _ = _started(db)
    a.post(f"/projects/{pid}/agreement/progress", json={"action": "hold"}, headers=_v(a, pid))
    assert _do(a, pid, "submit").status_code == 400  # on hold
    a.post(f"/projects/{pid}/agreement/progress", json={"action": "resume"}, headers=_v(a, pid))
    owner.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra", "value_change": "100"}, headers=_v(owner, pid))
    assert _do(a, pid, "submit").status_code == 400  # a change awaits an answer
    vid = _a(a, pid)["variations"][0]["id"]
    a.post(f"/projects/{pid}/agreement/variations/{vid}/reject", json={}, headers={})
    stale = _v(a, pid)
    owner.post(f"/projects/{pid}/agreement/progress", json={"action": "update", "note": "Seen."}, headers=_v(owner, pid))
    assert _do(a, pid, "submit", headers=stale).status_code == 409  # a stale page
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid))
    assert _do(a, pid, "submit").status_code == 400
    assert _do(owner, pid, "accept").status_code == 400


def test_nobody_else(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    for client in (b, _account(db, "service_provider", "rival@example.com", organization="Rival Contracting"), _account(db, "owner", "other@example.com", organization="Other Co")):
        for verb in ("submit", "accept", "return"):
            assert client.post(f"/projects/{pid}/agreement/completion/{verb}", json={"note": "x"}).status_code == 404
    assert _admin(db).post(f"/projects/{pid}/agreement/completion/accept", json={}).status_code == 403
    assert TestClient(app).post(f"/projects/{pid}/agreement/completion/accept", json={}).status_code == 401
    other = _tender(owner, title="Not awarded")
    assert owner.post(f"/projects/{other}/agreement/completion/accept", json={}).status_code == 404
    assert _a(owner, pid)["completion_status"] == "submitted"


def test_failures_leave_one_story(db, monkeypatch):
    owner, a, b, pid, wid, _ = _started(db)

    def broken(*args, **kwargs):
        raise RuntimeError("mail server down")

    monkeypatch.setattr(completion_router.notify_service, "notify_team", broken)
    assert _do(a, pid, "submit").status_code == 200  # stands without its notification
    monkeypatch.undo()

    def failing_log(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(completion_router.audit, "log_action", failing_log)
    try:
        _do(owner, pid, "accept")
    except RuntimeError:
        pass
    monkeypatch.undo()
    db.expire_all()
    assert db.query(Agreement).one().completion_status == "submitted"
    assert [u.kind for u in db.query(ExecutionUpdate).order_by(ExecutionUpdate.sequence)] == ["started", "delivered"]


@needs_mysql
def test_two_owner_tabs_and_a_resubmission_settle_on_one_outcome(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    calls = [lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/completion/accept", json={}),
             lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/completion/accept", json={}),
             lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/completion/return", json={"note": "Redo."})]
    with ThreadPoolExecutor(3) as pool:
        codes = sorted(f.result().status_code for f in [pool.submit(c) for c in calls])
    assert codes == [200, 409, 409], codes
    db.expire_all()
    final = db.query(Agreement).one().completion_status
    decisions = [u.kind for u in db.query(ExecutionUpdate).filter(ExecutionUpdate.milestone_id.is_(None), ExecutionUpdate.kind.in_(("accepted", "returned")))]
    assert decisions == [final]

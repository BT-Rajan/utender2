"""Stage 7.11: the transaction's final state. The owner's acceptance of the
whole work (7.10) closes it -- "completed", with a server time -- and from
then on nothing changes it: every write is refused at the agreement's one
door, whatever page or request it comes from. Completed is never confused
with terminated, and the history it rests on stays readable."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import ProjectStatus
from app.models.project import Project
from tests.stage7_helpers import put_in_force
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage7_10_completion import _a, _do, _milestone, _relogin, _started, _v

PDF = ("final-certificate.pdf", b"%PDF cert", "application/pdf")


def _complete(owner, a, pid):
    assert _do(a, pid, "submit", "Done.").status_code == 200
    r = _do(owner, pid, "accept", "Accepted.")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_simple_transaction_closes_on_acceptance_and_both_see_it(db):
    owner, a, b, pid, wid, _ = _started(db)
    before = datetime.utcnow().replace(microsecond=0) - timedelta(seconds=2)
    done = _complete(owner, a, pid)
    assert (done["status"], done["execution_status"], done["completion_status"]) == ("completed", "completed", "accepted")
    closed = datetime.fromisoformat(done["completed_at"].rstrip("Z"))
    assert before <= closed <= datetime.utcnow() + timedelta(seconds=2)  # server time
    for client in (owner, a, _admin(db)):
        seen = _a(client, pid)
        assert (seen["status"], seen["completed_at"], seen["owner_name"], seen["provider_name"], seen["current_amount"]) == (
            "completed", done["completed_at"], "Gulf Holdings W.L.L.", "amal", "1000.000")
    assert b.get(f"/projects/{pid}/agreement").status_code == 404
    (entry,) = db.query(AuditLog).filter(AuditLog.action == "completion.accept").all()
    assert entry.new_value == "accepted; transaction completed"
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded  # the requirement's own outcome stays "awarded"


def test_nothing_reopens_or_changes_a_completed_transaction(db):
    owner, a, b, pid, wid, _ = _started(db)
    doc = a.post(f"/projects/{pid}/agreement/documents", data={"kind": "site_report"}, files={"file": PDF}).json()["documents"][0]["id"]
    _complete(owner, a, pid)
    stale = {"If-Match": "1"}
    attempts = [
        a.post(f"/projects/{pid}/agreement/progress", json={"action": "update", "note": "More"}, headers={}),
        a.post(f"/projects/{pid}/agreement/progress", json={"action": "hold"}, headers={}),
        a.post(f"/projects/{pid}/agreement/start-work", json={}, headers={}),
        a.post(f"/projects/{pid}/agreement/documents", data={"kind": "progress_photo"}, files={"file": PDF}),
        a.delete(f"/projects/{pid}/agreement/documents/{doc}"),
        owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "Extra"}, headers={}),
        owner.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra", "value_change": "100"}, headers={}),
        owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "x"}, headers={}),
        owner.patch(f"/projects/{pid}/agreement", json={"reference": "X"}, headers=stale),
        _do(a, pid, "submit", headers={}),
        _do(owner, pid, "accept", headers={}),  # the browser's retry after success
        _do(owner, pid, "return", "Changed my mind.", headers=stale),  # an old page
    ]
    for r in attempts:
        assert r.status_code == 409, (r.request.url, r.status_code, r.text)
        assert "completed and closed" in r.json()["detail"]
    seen = _a(owner, pid)
    assert (seen["status"], seen["completion_status"], len(seen["documents"])) == ("completed", "accepted", 1)
    assert owner.get(f"/projects/{pid}/agreement/documents/{doc}/file", follow_redirects=False).status_code == 303  # evidence stays open
    assert db.query(AuditLog).filter(AuditLog.action == "completion.accept").count() == 1


def test_outstanding_deliverables_block_completion_then_all_accepted_completes(db):
    owner, a, b, pid, wid, ids = _started(db, milestones=("One", "Two", "Three"))
    for mid in ids[:2]:
        _milestone(a, pid, mid, "deliver")
        _milestone(owner, pid, mid, "accept")
    assert _do(a, pid, "submit").status_code == 400  # one still outstanding
    assert _a(owner, pid)["status"] == "active"
    _milestone(a, pid, ids[2], "deliver")
    _milestone(owner, pid, ids[2], "accept")
    done = _complete(owner, a, pid)
    assert done["status"] == "completed" and [m["status"] for m in done["milestones"]] == ["accepted"] * 3


def test_a_variation_is_kept_in_the_completed_record(db):
    owner, a, b, pid, wid, _ = _started(db)
    vid = owner.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra bay.", "value_change": "250"}, headers=_v(owner, pid)).json()["variations"][0]["id"]
    v = _a(a, pid)["variations"][0]
    a.post(f"/projects/{pid}/agreement/variations/{vid}/agree", json={}, headers={"If-Match": str(v["version"])})
    done = _complete(owner, a, pid)
    assert (done["original_amount"], done["current_amount"], done["variations"][0]["status"]) == ("1000.000", "1250.000", "agreed")
    db.expire_all()
    assert db.query(AwardRecord).one().amount == 1000


def test_terminated_or_cancelled_is_never_completed_by_a_stale_request(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    stale = _v(owner, pid)
    # Termination while the work awaits review is refused (the work is submitted); end it the other way round:
    _do(owner, pid, "return", "Not finished.")
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid))
    assert _do(owner, pid, "accept", headers=stale).status_code == 400  # terminated stays terminated
    assert _do(a, pid, "submit", headers={}).status_code == 400
    seen = _a(owner, pid)
    assert (seen["status"], seen["execution_status"], seen["completed_at"]) == ("terminated", "terminated", None)
    # A requirement cancelled before any award has no transaction to complete.
    owner2 = _account(db, "owner", "owner2@example.com")
    from tests.test_stage5_13_revise import _submitted, _tender

    pid2 = _tender(owner2, title="Cancelled")
    _submitted(a, pid2)
    owner2.post(f"/owner/projects/{pid2}/close")
    owner2.post(f"/owner/projects/{pid2}/cancel", json={"reason": "other"})
    assert owner2.post(f"/projects/{pid2}/agreement/completion/accept", json={}).status_code == 404


def test_only_the_owner_side_completes(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    assert _do(a, pid, "accept").status_code == 403
    for client in (b, _account(db, "owner", "other@example.com", organization="Other Co"), TestClient(app)):
        assert client.post(f"/projects/{pid}/agreement/completion/accept", json={}).status_code in (401, 404)
    assert _admin(db).post(f"/projects/{pid}/agreement/completion/accept", json={}).status_code == 403
    assert _a(owner, pid)["status"] == "active"


@needs_mysql
def test_two_owner_users_completing_at_once_close_it_once(db):
    from tests.test_organization_sharing import _organization
    from tests.test_stage5_13_revise import _submitted, _tender

    fahad, noura, *_ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(fahad)
    _submitted(a, pid)
    fahad.post(f"/owner/projects/{pid}/close")
    fahad.post(f"/owner/projects/{pid}/offers/{a.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    put_in_force(fahad, a, pid)  # Batch A: effective date (Kuwait today), provider confirms, owner activates
    a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid))
    _do(a, pid, "submit")
    calls = [lambda: _relogin("fahad@gulf.example").post(f"/projects/{pid}/agreement/completion/accept", json={}),
             lambda: _relogin("noura@gulf.example").post(f"/projects/{pid}/agreement/completion/accept", json={}),
             lambda: _relogin("amal@example.com").post(f"/projects/{pid}/agreement/progress", json={"action": "update", "note": "Late note"})]
    with ThreadPoolExecutor(3) as pool:
        codes = [f.result().status_code for f in [pool.submit(c) for c in calls]]
    assert sorted(codes[:2]) == [200, 409], codes
    db.expire_all()
    ag = db.query(Agreement).one()
    assert (ag.status, ag.completion_status) == ("completed", "accepted") and ag.completed_at is not None
    assert db.query(AuditLog).filter(AuditLog.action == "completion.accept").count() == 1

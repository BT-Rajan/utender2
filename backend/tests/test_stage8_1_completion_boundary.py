"""Stage 8.1: the completion point trust and reputation build on is Stage 7's
completed transaction -- the agreement closed by the owner side's acceptance
of the whole work. Nothing short of it, and no other ending, makes a
transaction eligible; the existing owner review of the provider now follows
that rule instead of opening at the award."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement
from app.models.award_record import AwardRecord
from app.models.review import Review
from app.services.transactions import completed_transaction
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage7_10_completion import _a, _do, _milestone, _relogin, _started, _v


def _review(owner, pid, rating=5):
    # service_provider_id is ignored: the server takes the provider from the award.
    return owner.post("/owner/reviews", json={"project_id": pid, "service_provider_id": "ignored", "rating": rating})


def test_only_a_completed_transaction_is_eligible(db):
    owner, a, b, pid, wid, (m1, m2) = _started(db, milestones=("Panels", "Report"))

    def not_yet():
        assert completed_transaction(db, pid) is None and _review(owner, pid).status_code == 400

    not_yet()  # executing
    a.post(f"/projects/{pid}/agreement/progress", json={"action": "hold"}, headers=_v(a, pid))
    not_yet()  # on hold
    a.post(f"/projects/{pid}/agreement/progress", json={"action": "resume"}, headers=_v(a, pid))
    _milestone(a, pid, m1, "deliver")
    _milestone(owner, pid, m1, "return", "Fix.")
    not_yet()  # a deliverable returned for correction
    for mid in (m1, m2):
        _milestone(a, pid, mid, "deliver")
        _milestone(owner, pid, mid, "accept")
    not_yet()  # every deliverable accepted, the work not yet submitted
    _do(a, pid, "submit")
    not_yet()  # delivered, awaiting the owner's acceptance
    _do(owner, pid, "accept")
    db.expire_all()
    done = completed_transaction(db, pid)
    assert done is not None and done.completed_at is not None
    for c in (owner, a):  # both parties see the same closed transaction
        seen = _a(c, pid)
        assert (seen["status"], seen["completed_at"]) == ("completed", done.completed_at.isoformat() + "Z")
    # The owner's review now opens -- once, and about the actual winner.
    r = _review(owner, pid)
    assert r.status_code == 200 and r.json()["service_provider_id"] == db.query(AwardRecord).one().service_provider_id
    assert db.query(Review).count() == 1 and _review(owner, pid).status_code == 409


def test_other_endings_are_never_eligible(db):
    # Terminated after the work started.
    owner, a, b, pid, wid, _ = _started(db)
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid))
    assert completed_transaction(db, pid) is None and _review(owner, pid).status_code == 400
    assert _a(owner, pid)["status"] == "terminated"
    # Cancelled, no award, closed externally: no transaction at all.
    for n, ending in enumerate(("cancel", "no-award", "close-externally")):
        o = _account(db, "owner", f"o{n}@example.com")
        sp = _account(db, "service_provider", f"sp{n}@example.com")
        p = _tender(o, title=f"Ended {n}")
        _submitted(sp, p)
        o.post(f"/owner/projects/{p}/close")
        o.post(f"/owner/projects/{p}/{ending}", json={"reason": "other"} if ending != "no-award" else {})
        assert completed_transaction(db, p) is None and _review(o, p).status_code == 400, ending


def test_nobody_else_can_complete_or_review_it(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    assert _do(a, pid, "accept").status_code == 403  # the provider can't complete its own work
    for c in (b, _account(db, "owner", "other@example.com", organization="Other Co"), TestClient(app)):
        assert c.post(f"/projects/{pid}/agreement/completion/accept", json={}).status_code in (401, 403, 404)
        assert _review(c, pid).status_code in (401, 403, 404)
    assert completed_transaction(db, pid) is None
    _do(owner, pid, "accept")
    stale = _do(owner, pid, "accept", headers={"If-Match": "1"})
    assert stale.status_code == 409 and _a(owner, pid)["status"] == "completed"  # a stale page changes nothing


@needs_mysql
def test_simultaneous_completion_is_one_completion(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    with ThreadPoolExecutor(3) as pool:
        codes = sorted(f.result().status_code for f in [pool.submit(lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/completion/accept", json={})) for _ in range(3)])
    assert codes == [200, 409, 409], codes
    db.expire_all()
    assert completed_transaction(db, pid) is not None

"""Stage 7.13: the transaction's history. One timeline, in time order, merged
from the records that already hold each event -- award, agreement in force,
agreement papers, execution history, deliverables, variations, completion --
written once and never changed: no retry duplicates it, no later state
rewrites it, and only the parties (and admins) read it."""
from fastapi.testclient import TestClient

from app.main import app
from app.models.award_record import AwardRecord
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage7_10_completion import _a, _do, _milestone, _started, _v

PDF = ("signed.pdf", b"%PDF signed", "application/pdf")


def _story(seen):
    return [(e["kind"], e["party"], e["milestone_title"] or e["variation_number"]) for e in seen["timeline"]]


def test_the_whole_story_in_order(db):
    owner, a, b, pid, wid, (m1, m2) = _started(db, milestones=("Panels", "Report"))
    owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "signed_agreement"}, files={"file": PDF})
    vid = owner.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra bay.", "value_change": "250"}, headers=_v(owner, pid)).json()["variations"][0]["id"]
    v = _a(a, pid)["variations"][0]
    a.post(f"/projects/{pid}/agreement/variations/{vid}/agree", json={}, headers={"If-Match": str(v["version"])})
    _milestone(a, pid, m1, "deliver")
    _milestone(owner, pid, m1, "return", "Misaligned.")
    _milestone(a, pid, m1, "deliver")
    _milestone(owner, pid, m1, "accept")
    _milestone(a, pid, m2, "deliver")
    _milestone(owner, pid, m2, "accept")
    _do(a, pid, "submit", "Done.")
    _do(owner, pid, "accept")
    _do(owner, pid, "accept", headers={})  # a browser retry after success: refused, adds nothing

    for client in (owner, a, _admin(db)):
        seen = _a(client, pid)
        story = _story(seen)
        kinds = [k for k, _, _ in story]
        assert kinds[:2] == ["awarded", "in_force"]
        assert kinds[-2:] == ["accepted", "completed"] and kinds.count("completed") == 1
        assert ("change_proposed", "owner", 1) in story and ("change_agreed", "provider", 1) in story
        assert ("document", "owner", None) in story and ("started", "provider", None) in story
        deliverables = [(k, p, t) for k, p, t in story if t in ("Panels", "Report")]
        assert deliverables == [  # each at its own moment, the return kept
            ("delivered", "provider", "Panels"), ("returned", "owner", "Panels"), ("delivered", "provider", "Panels"),
            ("accepted", "owner", "Panels"), ("delivered", "provider", "Report"), ("accepted", "owner", "Report"),
        ]
        whole = [(k, p) for k, p, t in story if t is None and k in ("delivered", "accepted")]
        assert whole == [("delivered", "provider"), ("accepted", "owner")]
        times = [e["at"] for e in seen["timeline"]]
        assert times == sorted(times) and all(t.endswith("Z") for t in times)
        awarded = seen["timeline"][0]
        assert awarded["amount"] == "1000.000"  # the original award, not the current value
        agreed = next(e for e in seen["timeline"] if e["kind"] == "change_agreed")
        assert (agreed["amount"], agreed["resulting_amount"]) == ("250.000", "1250.000")
        assert seen["current_amount"] == "1250.000" and seen["timeline"][-1]["at"] == seen["completed_at"]
    db.expire_all()
    assert db.query(AwardRecord).one().amount == 1000


def test_actor_names_stay_on_their_own_side_and_history_stays_private(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    _do(owner, pid, "accept")
    mine = {e["kind"]: e["actor_name"] for e in _a(owner, pid)["timeline"]}
    theirs = {e["kind"]: e["actor_name"] for e in _a(a, pid)["timeline"]}
    assert mine["awarded"] == "N" and theirs["awarded"] is None  # the owner's member, to the owner side only
    assert theirs["started"] == "N" and mine["started"] is None
    for client in (b, _account(db, "service_provider", "rival@example.com", organization="Rival Contracting"),
                   _account(db, "owner", "other@example.com", organization="Other Co"), TestClient(app)):
        assert client.get(f"/projects/{pid}/agreement").status_code in (401, 404)


def test_a_terminated_transaction_keeps_its_story(db):
    owner, a, b, pid, wid, _ = _started(db)
    owner.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra.", "value_change": "100"}, headers=_v(owner, pid))
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid))
    kinds = [e["kind"] for e in _a(a, pid)["timeline"]]
    assert kinds[-2:] == ["change_lapsed", "terminated"] and "completed" not in kinds

"""Stage 8.2: the transaction's outcome, as later trust steps will need it --
who did business with whom, on which requirement and offer, for what final
agreed value, how and when it ended -- is the Stage 7 record itself (award,
winning offer, agreement, variations, completion), written once and never
rewritten. No separate outcome record: these tests prove the existing one
answers every question, for the parties only, and that no other ending is
taken for completed business."""
from app.models.agreement import Agreement, Variation
from app.models.award_record import AwardRecord
from app.models.offer import Offer
from app.models.project import Project
from app.services.transactions import completed_transaction
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage7_10_completion import _a, _do, _started, _v


def _agree(proposer, answerer, pid, value):
    vid = proposer.post(f"/projects/{pid}/agreement/variations", json={"description": f"Change {value}", "value_change": value}, headers=_v(proposer, pid)).json()["variations"][-1]["id"]
    v = next(x for x in _a(answerer, pid)["variations"] if x["id"] == vid)
    assert answerer.post(f"/projects/{pid}/agreement/variations/{vid}/agree", json={}, headers={"If-Match": str(v["version"])}).status_code == 200


def test_a_completed_transaction_answers_who_what_value_how_and_when(db):
    owner, colleague, *_ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    winner = _account(db, "service_provider", "amal@example.com", organization="Amal Contracting")
    loser = _account(db, "service_provider", "badr@example.com")
    pid = _tender(owner)
    _submitted(winner, pid)
    _submitted(loser, pid)
    owner.post(f"/owner/projects/{pid}/close")
    wid = winner.get(f"/projects/{pid}/offers/mine").json()["id"]
    owner.post(f"/owner/projects/{pid}/offers/{wid}/approve")
    owner.patch(f"/projects/{pid}/agreement", json={"effective_date": "2030-01-01"}, headers=_v(owner, pid))
    owner.post(f"/projects/{pid}/agreement/activate", headers=_v(owner, pid))
    winner.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(winner, pid))
    _agree(winner, owner, pid, "300")    # two variations, agreed by the other party each time
    _agree(colleague, winner, pid, "-100")
    _do(winner, pid, "submit")
    _do(owner, pid, "accept")
    _do(owner, pid, "accept", headers={})  # a retry after a timeout: refused, changes nothing

    db.expire_all()
    done = completed_transaction(db, pid)
    award, project, offer = db.query(AwardRecord).one(), db.get(Project, pid), db.get(Offer, wid)
    # One outcome, tied to the right parties, requirement and offer.
    assert db.query(Agreement).filter(Agreement.project_id == pid).count() == 1
    assert (done.award_id, award.offer_id, award.service_provider_id) == (award.id, wid, offer.service_provider_id)
    assert (project.organization_id is not None, offer.organization_id is not None) == (True, True)
    assert award.project_revision <= project.revision  # the requirement version it was awarded on stays recorded
    for c in (owner, colleague, winner, _admin(db)):
        seen = _a(c, pid)
        assert (seen["status"], seen["completed_at"], seen["owner_name"], seen["provider_name"], seen["offer_id"]) == (
            "completed", done.completed_at.isoformat() + "Z", "Gulf Holdings W.L.L.", "Amal Contracting", wid)
        assert (seen["original_amount"], seen["agreed_changes_total"], seen["current_amount"], seen["currency"], seen["payment_tracking"]) == (
            "1000.000", "200.000", "1200.000", "KWD", "not_managed")
        assert [(v["status"], v["previous_amount"], v["resulting_amount"]) for v in seen["variations"]] == [
            ("agreed", "1000.000", "1300.000"), ("agreed", "1300.000", "1200.000")]
        assert [e["kind"] for e in seen["timeline"]].count("completed") == 1
    # Nobody else reads it.
    for c in (loser, _account(db, "owner", "other@example.com", organization="Other Co")):
        assert c.get(f"/projects/{pid}/agreement").status_code == 404
    # Nothing after completion rewrites it.
    assert owner.post(f"/projects/{pid}/agreement/variations", json={"description": "Late", "value_change": "999"}, headers={}).status_code == 409
    db.expire_all()
    assert (db.query(AwardRecord).one().amount, db.get(Offer, wid).amount, db.query(Variation).count()) == (1000, 1000, 2)
    assert completed_transaction(db, pid).completed_at == done.completed_at


def test_other_endings_stay_distinguishable_from_completed_business(db):
    owner, a, b, pid, wid, _ = _started(db)
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid))
    seen = _a(owner, pid)
    assert (seen["status"], seen["completed_at"], seen["termination_reason"]) == ("terminated", None, "Stopped.")
    assert completed_transaction(db, pid) is None
    endings = {}
    for n, ending in enumerate(("cancel", "no-award", "close-externally")):
        o = _account(db, "owner", f"o{n}@example.com")
        sp = _account(db, "service_provider", f"sp{n}@example.com")
        p = _tender(o, title=f"Ended {n}")
        _submitted(sp, p)
        o.post(f"/owner/projects/{p}/close")
        o.post(f"/owner/projects/{p}/{ending}", json={"reason": "other"} if ending != "no-award" else {})
        assert o.get(f"/projects/{p}/agreement").status_code == 404 and completed_transaction(db, p) is None
        db.expire_all()
        ended = db.get(Project, p)
        endings[ending] = (ended.status.value, ended.closure_reason)
    # Each ending stays its own (closed externally is "no award" with its own reason, as Stage 6 records it).
    assert len(set(endings.values())) == 3 and all(s != "awarded" for s, _ in endings.values()), endings


def test_the_helper_drives_the_real_flow(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{sp.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    assert complete_transaction(owner, sp, pid)["status"] == "completed"

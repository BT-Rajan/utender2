"""Stage 7.8: variations. After the agreement is in force, either party
proposes a change; it takes effect only when the other party agrees. The
current agreed value and completion are the original award plus the agreed
variations; each variation keeps what it changed from; the award, the
requirement, the winning offer and the original agreement never move."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import AgreementDocument, Milestone, Variation
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import NotificationType, OfferStatus, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import DECL, _d, _tender
from tests.stage7_helpers import put_in_force

PDF = ("change-order.pdf", b"%PDF change order", "application/pdf")


def _relogin(email):
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _offer(sp, pid, amount):
    sp.post(f"/projects/{pid}/participate")
    sp.put(f"/projects/{pid}/offers/draft", json={"amount": amount, "message": "Method", "assumptions": "A1", "accepted_declarations": [DECL],
                                                  "proposed_start_date": _d(20), "proposed_completion_date": _d(80)})
    sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("m.pdf", b"%PDF-m", "application/pdf")})
    assert sp.post(f"/projects/{pid}/offers/draft/submit").status_code == 200


def _a(client, pid):
    return client.get(f"/projects/{pid}/agreement").json()


def _v(client, pid):
    return {"If-Match": str(_a(client, pid)["version"])}


def _vv(client, pid, vid):
    return {"If-Match": str(next(x for x in _a(client, pid)["variations"] if x["id"] == vid)["version"])}


def _in_force(db, with_milestone=False):
    owner = _account(db, "owner", "owner@example.com", organization="Gulf Holdings W.L.L.")
    a, b = _account(db, "service_provider", "amal@example.com"), _account(db, "service_provider", "badr@example.com")
    pid = _tender(owner)
    _offer(a, pid, "10000")
    _offer(b, pid, "9000")
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    wid = a.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    mid = None
    if with_milestone:
        r = owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "Panels installed", "due_date": _d(60)}, headers=_v(owner, pid))
        mid = r.json()["milestones"][0]["id"]
    put_in_force(owner, a, pid)  # Batch A: effective today (Kuwait), confirmed by the provider, then activated
    assert a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid)).status_code == 200
    return owner, a, b, pid, wid, mid


def _propose(client, pid, **body):
    return client.post(f"/projects/{pid}/agreement/variations", json=body, headers=_v(client, pid))


def _answer(client, pid, vid, verb, note=None, headers=None):
    return client.post(f"/projects/{pid}/agreement/variations/{vid}/{verb}", json={"note": note} if verb != "withdraw" else None,
                       headers=_vv(client, pid, vid) if headers is None else headers)


def test_a_price_variation_keeps_the_original(db):
    owner, a, b, pid, wid, _ = _in_force(db)
    r = _propose(a, pid, description="Additional cladding on the east wall.", value_change="1000")
    assert r.status_code == 200, r.text
    vid = r.json()["variations"][0]["id"]
    pending = _a(owner, pid)
    assert (pending["variations"][0]["status"], pending["original_amount"], pending["current_amount"]) == ("proposed", "10000.000", "10000.000")  # not yet
    assert _answer(a, pid, vid, "agree").status_code == 403  # a provider can't agree its own price change
    r = _answer(owner, pid, vid, "agree", "Approved by the board.")
    assert r.status_code == 200
    for client in (owner, a, _admin(db)):
        seen = _a(client, pid)
        v = seen["variations"][0]
        assert (seen["original_amount"], seen["current_amount"]) == ("10000.000", "11000.000")
        assert (v["status"], v["number"], v["previous_amount"], v["resulting_amount"], v["proposed_party"], v["decided_party"]) == ("agreed", 1, "10000.000", "11000.000", "provider", "owner")
    db.expire_all()
    assert db.query(AwardRecord).one().amount == 10000  # the award is never rewritten
    assert db.get(Offer, wid).amount == 10000 and db.get(Offer, wid).status == OfferStatus.approved
    assert db.get(Project, pid).status == ProjectStatus.awarded
    # A later reduction builds on the current agreed value.
    vid2 = _propose(owner, pid, description="Omit the canopy.", value_change="-500").json()["variations"][1]["id"]
    _answer(a, pid, vid2, "agree")
    seen = _a(owner, pid)
    assert (seen["current_amount"], seen["variations"][1]["previous_amount"], seen["variations"][1]["resulting_amount"]) == ("10500.000", "11000.000", "10500.000")
    actions = sorted(e.action for e in db.query(AuditLog).filter(AuditLog.action.like("variation.%")))
    assert actions == ["variation.agree", "variation.agree", "variation.propose", "variation.propose"]


def test_scope_and_date_variations_keep_the_original(db):
    owner, a, b, pid, wid, mid = _in_force(db, with_milestone=True)
    original = _a(owner, pid)
    assert (original["original_completion_date"], original["original_completion_source"]) == (_d(80), "offer")
    r = _propose(owner, pid, description="Add a rooftop plant screen; finish later.", completion_date=_d(110),
                 milestone_id=mid, milestone_due_date=_d(75), add_deliverable="Plant screen installed")
    vid = r.json()["variations"][0]["id"]
    assert _a(a, pid)["milestones"][0]["due_date"] == _d(60)  # nothing moves while proposed
    _answer(a, pid, vid, "agree")
    seen = _a(owner, pid)
    v = seen["variations"][0]
    assert (seen["original_completion_date"], seen["current_completion_date"], v["previous_completion_date"]) == (_d(80), _d(110), _d(80))
    assert (seen["milestones"][0]["due_date"], v["previous_milestone_due_date"], v["milestone_title"]) == (_d(75), _d(60), "Panels installed")
    added = seen["milestones"][1]
    assert (added["title"], added["status"], added["variation_number"]) == ("Plant screen installed", "pending", 1)
    assert seen["milestones"][0]["variation_number"] is None  # an original deliverable
    # The original requirement and award are as they were.
    db.expire_all()
    p = db.get(Project, pid)
    assert p.expected_completion_date is None and db.query(AwardRecord).one().amount == 10000
    # Papers of the variation are tied to it, and to this agreement only.
    r = owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "change_order", "variation_id": vid}, files={"file": PDF})
    assert r.status_code == 200 and r.json()["documents"][0]["variation_id"] == vid


def test_unilateral_changes_are_blocked(db):
    owner, a, b, pid, wid, mid = _in_force(db, with_milestone=True)
    # No direct edits once in force: agreement details, deliverables.
    assert owner.patch(f"/projects/{pid}/agreement", json={"reference": "X"}, headers=_v(owner, pid)).status_code == 400
    assert owner.patch(f"/projects/{pid}/agreement/milestones/{mid}", json={"title": "Other"}, headers={}).status_code == 400
    vid = _propose(a, pid, description="Price rise.", value_change="2500").json()["variations"][0]["id"]
    assert _answer(a, pid, vid, "agree").status_code == 403
    assert _answer(a, pid, vid, "reject").status_code == 403
    assert _answer(owner, pid, vid, "withdraw").status_code == 403  # only the proposer withdraws
    assert _a(owner, pid)["current_amount"] == "10000.000"
    assert _answer(owner, pid, vid, "reject", "Not agreed.").json()["variations"][0]["status"] == "rejected"
    assert _a(a, pid)["current_amount"] == "10000.000"
    # Bad proposals.
    assert _propose(a, pid, description="  ").status_code == 400
    assert _propose(a, pid, description="x", value_change="0").status_code == 400
    assert _propose(a, pid, description="x", value_change="-10000").status_code == 400  # value can't reach zero
    assert _propose(a, pid, description="x", completion_date=_d(-60)).status_code == 400
    assert _propose(a, pid, description="x", milestone_id="not-one", milestone_due_date=_d(30)).status_code == 404


def test_only_one_open_proposal_and_answers_once(db):
    owner, a, b, pid, wid, _ = _in_force(db)
    vid = _propose(owner, pid, description="Extra lighting.", value_change="300").json()["variations"][0]["id"]
    r = _propose(a, pid, description="Something else.")
    assert r.status_code == 409 and "already awaiting an answer" in r.json()["detail"]
    stale = _vv(a, pid, vid)
    assert _answer(a, pid, vid, "agree", headers=stale).status_code == 200
    r = _answer(a, pid, vid, "agree", headers=stale)  # the double-click
    assert r.status_code == 409 and "already agreed" in r.json()["detail"]
    assert _answer(owner, pid, vid, "withdraw", headers={}).status_code == 409  # too late to withdraw
    assert _a(owner, pid)["current_amount"] == "10300.000"
    vid2 = _propose(a, pid, description="Second.").json()["variations"][1]["id"]
    assert _answer(a, pid, vid2, "withdraw").json()["variations"][1]["status"] == "withdrawn"
    assert _answer(owner, pid, vid2, "agree", headers={}).status_code == 409
    notes = db.query(Notification).filter(Notification.type == NotificationType.variation_updated)
    assert {n.link for n in notes} == {f"/owner/projects/{pid}", f"/service-provider/projects/{pid}/offer"}
    b_id = b.get("/auth/me").json()["id"]
    assert notes.filter(Notification.user_id == b_id).count() == 0


def test_nobody_else_and_no_other_transaction(db):
    owner, a, b, pid, wid, _ = _in_force(db)
    vid = _propose(owner, pid, description="Extra.", value_change="100").json()["variations"][0]["id"]
    others = (b, _account(db, "service_provider", "rival@example.com", organization="Rival Contracting"), _account(db, "owner", "other@example.com", organization="Other Co"))
    for client in others:
        assert client.post(f"/projects/{pid}/agreement/variations", json={"description": "x"}).status_code == 404
        assert client.post(f"/projects/{pid}/agreement/variations/{vid}/agree", json={}).status_code == 404
        assert client.post(f"/projects/{pid}/agreement/documents", data={"kind": "change_order", "variation_id": vid}, files={"file": PDF}).status_code == 404
    assert TestClient(app).post(f"/projects/{pid}/agreement/variations", json={"description": "x"}).status_code == 401
    assert _admin(db).post(f"/projects/{pid}/agreement/variations/{vid}/agree", json={}).status_code == 403
    # Another transaction of the same owner and winner: its variation id is not found here.
    pid2 = _tender(owner, title="Second job")
    _offer(a, pid2, "500")
    owner.post(f"/owner/projects/{pid2}/close")
    owner.post(f"/owner/projects/{pid2}/offers/{a.get(f'/projects/{pid2}/offers/mine').json()['id']}/approve")
    put_in_force(owner, a, pid2)  # Batch A: the provider confirms before activation
    assert a.post(f"/projects/{pid2}/agreement/variations/{vid}/agree", json={}).status_code == 404
    assert a.post(f"/projects/{pid2}/agreement/documents", data={"kind": "change_order", "variation_id": vid}, files={"file": PDF}).status_code == 404
    assert db.get(Variation, vid).status == "proposed" and db.query(AgreementDocument).count() == 0


def test_terminal_or_unready_transactions_take_no_changes(db):
    owner, a, b, pid, wid, _ = _in_force(db)
    vid = _propose(a, pid, description="Extra.", value_change="100").json()["variations"][0]["id"]
    assert owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid)).status_code == 200
    seen = _a(owner, pid)
    assert (seen["variations"][0]["status"], seen["current_amount"], seen["execution_status"]) == ("lapsed", "10000.000", "terminated")
    r = _answer(owner, pid, vid, "agree", headers={})
    assert r.status_code == 409 and "closed when the agreement ended" in r.json()["detail"]
    assert _propose(owner, pid, description="After the end.").status_code == 400
    # Still being prepared: changes go into the agreement itself, not a variation.
    owner2 = _account(db, "owner", "owner2@example.com")
    pid2 = _tender(owner2, title="Prep")
    _offer(a, pid2, "700")
    owner2.post(f"/owner/projects/{pid2}/close")
    owner2.post(f"/owner/projects/{pid2}/offers/{a.get(f'/projects/{pid2}/offers/mine').json()['id']}/approve")
    assert _propose(owner2, pid2, description="Early.").status_code == 400
    # No award: nothing to vary.
    pid3 = _tender(owner2, title="Open")
    assert owner2.post(f"/projects/{pid3}/agreement/variations", json={"description": "x"}).status_code == 404
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded  # nothing reopened


def test_an_accepted_deliverable_cannot_be_rescheduled(db):
    owner, a, b, pid, wid, mid = _in_force(db, with_milestone=True)
    # Batch A: a revised due date can't fall after the completion date in force (_d(80)), so _d(70) instead of _d(90).
    vid = _propose(owner, pid, description="Move the panels date.", milestone_id=mid, milestone_due_date=_d(70)).json()["variations"][0]["id"]
    m = _a(a, pid)["milestones"][0]
    a.post(f"/projects/{pid}/agreement/milestones/{mid}/deliver", json={}, headers={"If-Match": str(m["version"])})
    m = _a(owner, pid)["milestones"][0]
    owner.post(f"/projects/{pid}/agreement/milestones/{mid}/accept", json={}, headers={"If-Match": str(m["version"])})
    r = _answer(a, pid, vid, "agree")
    assert r.status_code == 409 and "accepted meanwhile" in r.json()["detail"]
    assert _a(owner, pid)["milestones"][0]["due_date"] == _d(60)


@needs_mysql
def test_simultaneous_proposals_and_answers_are_consistent(db):
    owner, a, b, pid, wid, _ = _in_force(db)
    clients = [_relogin("owner@example.com"), _relogin("amal@example.com"), _relogin("owner@example.com"), _relogin("amal@example.com")]
    with ThreadPoolExecutor(4) as pool:
        codes = sorted(r.status_code for r in pool.map(lambda c: c.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra.", "value_change": "100"}), clients))
    assert codes == [200, 409, 409, 409], codes
    (v,) = db.query(Variation).all()
    answerer = "amal@example.com" if v.proposed_party == "owner" else "owner@example.com"
    proposer = "owner@example.com" if v.proposed_party == "owner" else "amal@example.com"
    calls = [lambda: _relogin(answerer).post(f"/projects/{pid}/agreement/variations/{v.id}/agree", json={}),
             lambda: _relogin(answerer).post(f"/projects/{pid}/agreement/variations/{v.id}/agree", json={}),
             lambda: _relogin(proposer).post(f"/projects/{pid}/agreement/variations/{v.id}/withdraw")]
    with ThreadPoolExecutor(3) as pool:
        results = [f.result().status_code for f in [pool.submit(c) for c in calls]]
    assert sorted(results) == [200, 409, 409], results
    db.expire_all()
    final = db.get(Variation, v.id).status
    assert final in ("agreed", "withdrawn")
    assert _a(owner, pid)["current_amount"] == ("10100.000" if final == "agreed" else "10000.000")
    assert db.query(AuditLog).filter(AuditLog.action.in_(("variation.agree", "variation.withdraw"))).count() == 1

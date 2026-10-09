"""Stage 7.7: deliverables. The owner side sets them out while the agreement
is being prepared (optionally from the requirement's own items); once in
force they stay as agreed. After the start the winner delivers each, with
evidence; the owner side accepts it or returns it for correction -- delivered
is not accepted. One history, one audit trail, the other party told; nobody
else sees or touches any of it; the requirement, offer and award never move."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import AgreementDocument, ExecutionUpdate, Milestone
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import NotificationType, OfferStatus, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.project import Project, ProjectItem
from app.routers import milestones as milestones_router
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _d, _submitted, _tender
from tests.stage7_helpers import put_in_force

PDF = ("delivery-note.pdf", b"%PDF delivery", "application/pdf")


def _relogin(email):
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _agreement(client, pid):
    return client.get(f"/projects/{pid}/agreement").json()


def _v(client, pid):
    return {"If-Match": str(_agreement(client, pid)["version"])}


def _mv(client, pid, mid):
    return {"If-Match": str(next(m for m in _agreement(client, pid)["milestones"] if m["id"] == mid)["version"])}


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


def _add(owner, pid, title, **extra):
    r = owner.post(f"/projects/{pid}/agreement/milestones", json={"title": title, **extra}, headers=_v(owner, pid))
    assert r.status_code == 200, r.text
    return next(m for m in r.json()["milestones"] if m["title"] == title)["id"]


def _start(a, pid):
    assert a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid)).status_code == 200


def _deliver(a, pid, mid, note=None, headers=None):
    return a.post(f"/projects/{pid}/agreement/milestones/{mid}/deliver", json={"note": note}, headers=_mv(a, pid, mid) if headers is None else headers)


def _decide(owner, pid, mid, verb, note=None, headers=None):
    return owner.post(f"/projects/{pid}/agreement/milestones/{mid}/{verb}", json={"note": note}, headers=_mv(owner, pid, mid) if headers is None else headers)


def test_set_out_delivered_returned_redelivered_accepted(db):
    owner, a, b, pid, wid = _awarded(db)
    award = db.query(AwardRecord).one()
    before = (award.amount, award.offer_id)
    item = ProjectItem(project_id=pid, position=1, description="Supply 4 transformers", quantity=Decimal("4"), unit="nos")
    db.add(item)
    db.commit()

    m1 = _add(owner, pid, "Transformers delivered to site", project_item_id=item.id, due_date=_d(40), description="All four, with test certificates.")
    m2 = _add(owner, pid, "Commissioning report")
    seen = _agreement(a, pid)["milestones"]  # the winner sees them while preparing
    assert [(m["position"], m["title"], m["status"], m["project_item_label"]) for m in seen] == [
        (1, "Transformers delivered to site", "pending", "1. Supply 4 transformers"), (2, "Commissioning report", "pending", None),
    ]
    # In force: what was agreed stays as agreed.
    put_in_force(owner, a, pid)  # Batch A: effective today (Kuwait), with the provider's confirmation
    assert owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "Extra"}, headers=_v(owner, pid)).status_code == 400
    assert owner.patch(f"/projects/{pid}/agreement/milestones/{m2}", json={"title": "Changed"}, headers=_mv(owner, pid, m2)).status_code == 400
    assert owner.delete(f"/projects/{pid}/agreement/milestones/{m2}", headers=_mv(owner, pid, m2)).status_code == 400

    assert _deliver(a, pid, m1).status_code == 400  # the work hasn't started
    _start(a, pid)
    ev = a.post(f"/projects/{pid}/agreement/documents", data={"kind": "other", "milestone_id": m1}, files={"file": PDF})
    assert ev.status_code == 200 and ev.json()["documents"][0]["milestone_id"] == m1
    r = _deliver(a, pid, m1, "Delivered, see delivery note.")
    assert r.status_code == 200 and r.json()["milestones"][0]["status"] == "delivered" and r.json()["milestones"][0]["delivered_at"].endswith("Z")
    assert _agreement(owner, pid)["milestones"][0]["status"] == "delivered"  # not accepted by delivering

    assert _decide(owner, pid, m1, "return").status_code == 400  # a return says what to correct
    assert _decide(owner, pid, m1, "return", "One certificate missing.").json()["milestones"][0]["status"] == "returned"
    assert _deliver(a, pid, m1, "Certificate added.").json()["milestones"][0]["status"] == "delivered"
    r = _decide(owner, pid, m1, "accept", "All good.")
    assert r.json()["milestones"][0]["status"] == "accepted"
    assert _deliver(a, pid, m1).status_code == 409  # accepted is final
    assert a.post(f"/projects/{pid}/agreement/documents", data={"kind": "other", "milestone_id": m1}, files={"file": PDF}).status_code == 400

    history = [(h["kind"], h["party"], h["milestone_title"]) for h in _agreement(a, pid)["execution_history"]]
    assert history == [
        ("started", "provider", None),
        ("delivered", "provider", "Transformers delivered to site"), ("returned", "owner", "Transformers delivered to site"),
        ("delivered", "provider", "Transformers delivered to site"), ("accepted", "owner", "Transformers delivered to site"),
    ]
    actions = sorted(e.action for e in db.query(AuditLog).filter(AuditLog.action.like("milestone.%")))
    assert actions == sorted(["milestone.create", "milestone.create", "milestone.deliver", "milestone.return", "milestone.deliver", "milestone.accept"])
    # The owner side was told of each delivery, the winner of each decision -- unread ones merge per page.
    assert {n.link for n in db.query(Notification).filter(Notification.type == NotificationType.milestone_updated)} == {
        f"/owner/projects/{pid}", f"/service-provider/projects/{pid}/offer",
    }
    b_id = b.get("/auth/me").json()["id"]
    assert db.query(Notification).filter(Notification.user_id == b_id, Notification.type == NotificationType.milestone_updated).count() == 0

    db.expire_all()
    award = db.query(AwardRecord).one()
    assert (award.amount, award.offer_id) == before
    assert (db.get(Project, pid).status, db.get(Offer, wid).status) == (ProjectStatus.awarded, OfferStatus.approved)
    assert db.get(ProjectItem, item.id).description == "Supply 4 transformers"


def test_a_simple_job_needs_no_deliverables(db):
    owner, a, b, pid, wid = _awarded(db)
    put_in_force(owner, a, pid)  # Batch A: work starts only under an agreement in force
    _start(a, pid)
    seen = _agreement(owner, pid)
    assert seen["milestones"] == [] and seen["execution_status"] == "in_progress"
    assert a.post(f"/projects/{pid}/agreement/progress", json={"action": "update", "note": "Done today."}, headers=_v(a, pid)).status_code == 200


def test_who_may_do_what_and_ids_from_elsewhere(db):
    owner, a, b, pid, wid = _awarded(db)
    m = _add(owner, pid, "Report")
    put_in_force(owner, a, pid)  # Batch A: work starts only under an agreement in force
    _start(a, pid)
    assert a.post(f"/projects/{pid}/agreement/milestones", json={"title": "Mine"}, headers=_v(a, pid)).status_code == 403  # the owner side sets them out
    assert _decide(a, pid, m, "accept", headers={}).status_code == 403  # a provider can't accept its own delivery
    assert _deliver(owner, pid, m, headers={}).status_code == 403  # nor the owner deliver
    others = (b, _account(db, "service_provider", "rival@example.com", organization="Rival Contracting"), _account(db, "owner", "other@example.com", organization="Other Co"))
    for client in others:
        assert client.post(f"/projects/{pid}/agreement/milestones/{m}/deliver", json={}).status_code == 404
        assert client.post(f"/projects/{pid}/agreement/milestones/{m}/accept", json={}).status_code == 404
        assert client.post(f"/projects/{pid}/agreement/documents", data={"kind": "other", "milestone_id": m}, files={"file": PDF}).status_code == 404
    assert _admin(db).post(f"/projects/{pid}/agreement/milestones/{m}/accept", json={}).status_code == 403
    assert TestClient(app).post(f"/projects/{pid}/agreement/milestones/{m}/deliver", json={}).status_code == 401

    # A deliverable of another transaction (same owner, same winner), named under this one.
    pid2 = _tender(owner, title="Second")
    _submitted(a, pid2)
    owner.post(f"/owner/projects/{pid2}/close")
    owner.post(f"/owner/projects/{pid2}/offers/{a.get(f'/projects/{pid2}/offers/mine').json()['id']}/approve")
    m_other = _add(owner, pid2, "Other job's report")
    assert _deliver(a, pid, m_other, headers={}).status_code == 404
    assert _decide(owner, pid, m_other, "accept", headers={}).status_code == 404
    assert a.post(f"/projects/{pid}/agreement/documents", data={"kind": "other", "milestone_id": m_other}, files={"file": PDF}).status_code == 404
    assert owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "x", "project_item_id": "not-an-item"}, headers=_v(owner, pid)).status_code == 400
    assert db.get(Milestone, m_other).status == "pending" and db.query(AgreementDocument).count() == 0


def test_dates_and_set_out_rules(db):
    owner, a, b, pid, wid = _awarded(db)
    assert owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "Old", "due_date": _d(-30)}, headers=_v(owner, pid)).status_code == 400
    assert owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "   "}, headers=_v(owner, pid)).status_code == 400
    m = _add(owner, pid, "Report", due_date=_d(30))
    assert owner.patch(f"/projects/{pid}/agreement/milestones/{m}", json={"title": "Final report", "due_date": _d(45)}, headers=_mv(owner, pid, m)).status_code == 200
    stale = {"If-Match": "1"}
    assert owner.patch(f"/projects/{pid}/agreement/milestones/{m}", json={"title": "Other"}, headers=stale).status_code == 409
    seen = _agreement(owner, pid)["milestones"][0]
    assert (seen["title"], seen["due_date"]) == ("Final report", _d(45))
    assert owner.delete(f"/projects/{pid}/agreement/milestones/{m}", headers=_mv(owner, pid, m)).json()["milestones"] == []


def test_stale_pages_repeats_holds_and_endings(db, monkeypatch):
    owner, a, b, pid, wid = _awarded(db)
    m = _add(owner, pid, "Batch 1")
    m2 = _add(owner, pid, "Batch 2")  # Batch A: set out while being prepared -- work needs the agreement in force
    put_in_force(owner, a, pid)
    _start(a, pid)
    stale = _mv(a, pid, m)
    assert _deliver(a, pid, m, headers=stale).status_code == 200
    assert _deliver(a, pid, m, headers=stale).status_code == 409  # the second tab: already delivered, explained
    assert "already delivered" in _deliver(a, pid, m, headers={}).json()["detail"]
    fresh = _mv(owner, pid, m)
    assert _decide(owner, pid, m, "accept", headers=fresh).status_code == 200
    assert _decide(owner, pid, m, "return", "No.", headers=fresh).status_code == 409  # the colleague's late return

    # Batch A: in force, no more can be set out (previously added after the start while still preparing).
    assert owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "Batch 3"}, headers=_v(owner, pid)).status_code == 400
    a.post(f"/projects/{pid}/agreement/progress", json={"action": "hold"}, headers=_v(a, pid))
    assert _deliver(a, pid, m2).status_code == 400  # on hold
    a.post(f"/projects/{pid}/agreement/progress", json={"action": "resume"}, headers=_v(a, pid))

    def broken(*args, **kwargs):
        raise RuntimeError("mail server down")

    monkeypatch.setattr(milestones_router.notify_service, "notify_team", broken)
    assert _deliver(a, pid, m2).status_code == 200  # stands without its notification
    monkeypatch.undo()
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid))
    assert _decide(owner, pid, m2, "accept").status_code == 400  # terminated: nothing continues
    assert _agreement(a, pid)["milestones"][1]["status"] == "delivered"


def test_a_failed_save_records_nothing(db, monkeypatch):
    owner, a, b, pid, wid = _awarded(db)
    m = _add(owner, pid, "Report")
    put_in_force(owner, a, pid)  # Batch A: work starts only under an agreement in force
    _start(a, pid)

    def failing_log(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(milestones_router.audit, "log_action", failing_log)
    with pytest.raises(RuntimeError):
        _deliver(a, pid, m)
    monkeypatch.undo()
    db.expire_all()
    assert db.get(Milestone, m).status == "pending"
    # Batch A: putting the agreement in force now records the provider's confirmation and the activation first.
    assert [u.kind for u in db.query(ExecutionUpdate).order_by(ExecutionUpdate.sequence)] == ["terms_confirmed", "in_force", "started"]


def test_no_award_no_deliverables(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    assert owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "x"}).status_code == 404
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "other"})
    assert owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "x"}).status_code == 404
    assert db.query(Milestone).count() == 0


@needs_mysql
def test_accept_and_return_at_once_is_one_decision(db):
    owner, a, b, pid, wid = _awarded(db)
    m = _add(owner, pid, "Report")
    put_in_force(owner, a, pid)  # Batch A: work starts only under an agreement in force
    _start(a, pid)
    _deliver(a, pid, m)
    calls = [lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/milestones/{m}/accept", json={}),
             lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/milestones/{m}/return", json={"note": "Redo."}),
             lambda: _relogin("amal@example.com").post(f"/projects/{pid}/agreement/milestones/{m}/deliver", json={})]
    with ThreadPoolExecutor(3) as pool:
        codes = [f.result().status_code for f in [pool.submit(c) for c in calls]]
    db.expire_all()
    # However they interleave, the requests apply one at a time: the recorded
    # events form a valid chain, and the deliverable ends in the last one's
    # state. (Return -> re-deliver -> accept is a legitimate order.)
    events = [u.kind for u in db.query(ExecutionUpdate).filter(ExecutionUpdate.milestone_id == m).order_by(ExecutionUpdate.sequence)]
    allowed = {"pending": {"delivered"}, "delivered": {"accepted", "returned"}, "returned": {"delivered"}, "accepted": set()}
    state = "pending"
    for kind in events:
        assert kind in allowed[state], (state, kind, events)
        state = kind
    assert db.get(Milestone, m).status == state
    assert codes.count(200) == len(events) - 1, (codes, events)  # every success left exactly one event

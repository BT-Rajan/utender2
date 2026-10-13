"""PR 22 review fixes: a paper of the terms linked to a deliverable still needs
the provider's confirmation again, the last live offer withdrawn after the
close expires the requirement, and the deadline notice counts only the
offers the owner can see."""
from datetime import datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.enums import NotificationType, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.project import Project
from app.routers.agreements import kuwait_today
from tests.test_batch_a_contract_logic import _awarded, _v
from tests.test_batch_b_tender_fairness import _validity_tender
from tests.test_owner_journey_fixes import _deadline_passes
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender

PDF = {"file": ("scope.pdf", b"%PDF scope", "application/pdf")}


def _me(c):
    return c.get("/auth/me").json()["id"]


def _notices(db, client, kind):
    return db.query(Notification).filter(Notification.user_id == _me(client), Notification.type == kind).all()


# 1 -----------------------------------------------------------------------


def test_a_paper_of_the_terms_linked_to_a_deliverable_needs_the_provider_to_confirm_again(db):
    owner, sp, pid, base = _awarded(db, "linkedpaper")
    assert owner.patch(base, json={"effective_date": kuwait_today().isoformat()}, headers=_v(owner, pid)).status_code == 200
    assert owner.post(f"{base}/milestones", json={"title": "Roof membrane"}, headers=_v(owner, pid)).status_code == 200
    mid = owner.get(base).json()["milestones"][0]["id"]
    assert sp.post(f"{base}/confirm", headers=_v(sp, pid)).status_code == 200
    stale = _v(sp, pid)
    told = len(_notices(db, sp, NotificationType.tender_amendment))
    r = owner.post(f"{base}/documents", data={"kind": "agreed_scope", "milestone_id": mid}, files=PDF)
    assert r.status_code == 200, r.text
    assert r.json()["provider_confirmed_at"] is None and r.json()["version"] != int(stale["If-Match"])
    assert len(_notices(db, sp, NotificationType.tender_amendment)) == told + 1
    # Not in force on paperwork the provider never confirmed.
    assert owner.post(f"{base}/activate", headers=_v(owner, pid)).status_code == 400
    assert sp.post(f"{base}/confirm", headers=stale).status_code == 409
    # Taking it away again is a change of the terms too.
    assert sp.post(f"{base}/confirm", headers=_v(sp, pid)).status_code == 200
    doc_id = r.json()["documents"][0]["id"]
    r = owner.delete(f"{base}/documents/{doc_id}")
    assert r.status_code == 200 and r.json()["provider_confirmed_at"] is None
    assert owner.post(f"{base}/activate", headers=_v(owner, pid)).status_code == 400


# 2 -----------------------------------------------------------------------


def _lapsed_after_close(db, pid):
    project = db.get(Project, pid)
    project.closed_at = datetime.utcnow() - timedelta(days=11)
    db.commit()
    return project.closed_at


def test_the_last_live_offer_withdrawn_after_the_close_expires_the_requirement(db):
    owner = _account(db, "owner", "o-lastwd@example.com")
    sp = _account(db, "service_provider", "s-lastwd@example.com")
    pid = _validity_tender(owner, days=10)
    _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    closed_at = _lapsed_after_close(db, pid)
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    db.expire_all()
    project = db.get(Project, pid)
    assert project.status == ProjectStatus.expired and project.closed_at == closed_at
    audit = db.query(AuditLog).filter(AuditLog.action == "project.expire", AuditLog.target_id == pid).one()
    assert audit.previous_value == "closed" and audit.new_value == "expired" and audit.actor_id == _me(sp)
    expired = _notices(db, owner, NotificationType.requirement_expired)
    assert len(expired) == 1 and expired[0].link == f"/owner/projects/{pid}"
    # Nothing was there to judge "no suitable offer" on.
    assert owner.post(f"/owner/projects/{pid}/no-award", json={"reason": "no_suitable_offer"}).status_code == 400


def test_a_post_close_withdrawal_leaves_the_requirement_closed_while_another_offer_is_live(db):
    owner = _account(db, "owner", "o-onewd@example.com")
    a = _account(db, "service_provider", "s-onewd-a@example.com")
    b = _account(db, "service_provider", "s-onewd-b@example.com")
    pid = _validity_tender(owner, days=10)
    _submitted(a, pid)
    _submitted(b, pid)
    # Still an offer, though an admin has suspended it: held until reactivated.
    db.get(Offer, b.get(f"/projects/{pid}/offers/mine").json()["id"]).is_suspended = True
    db.commit()
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/start-evaluation").status_code == 200
    _lapsed_after_close(db, pid)
    assert a.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.under_evaluation
    assert not _notices(db, owner, NotificationType.requirement_expired)


# 3 -----------------------------------------------------------------------


def test_the_deadline_notice_counts_only_the_offers_the_owner_can_see(db):
    owner = _account(db, "owner", "o-seen@example.com")
    a = _account(db, "service_provider", "s-seen-a@example.com")
    b = _account(db, "service_provider", "s-seen-b@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    db.get(Offer, b.get(f"/projects/{pid}/offers/mine").json()["id"]).is_suspended = True
    db.commit()
    _deadline_passes(db, pid)
    owner.get("/owner/projects")
    assert len(owner.get(f"/owner/projects/{pid}/offers").json()) == 1
    ready = _notices(db, owner, NotificationType.evaluation_ready)
    assert len(ready) == 1 and "with 1 offer(s)" in ready[0].body


def test_the_deadline_notice_on_only_suspended_offers_says_they_are_under_review(db):
    owner = _account(db, "owner", "o-review@example.com")
    sp = _account(db, "service_provider", "s-review@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    db.get(Offer, sp.get(f"/projects/{pid}/offers/mine").json()["id"]).is_suspended = True
    db.commit()
    _deadline_passes(db, pid)
    owner.get("/owner/projects")
    assert db.get(Project, pid).status == ProjectStatus.closed  # the decision itself is unchanged
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    ready = _notices(db, owner, NotificationType.evaluation_ready)
    assert len(ready) == 1
    assert "offer(s)" not in ready[0].body and "Open it to evaluate" not in ready[0].body and "under review by a site admin" in ready[0].body

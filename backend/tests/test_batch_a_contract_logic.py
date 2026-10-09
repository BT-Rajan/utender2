"""Batch A: the post-award contract and execution follow the order a real
contract does. Each test is one of the business-logic faults found in the
end-to-end review, now refused or corrected:

- work only under an agreement in force, and not before its effective date;
- the provider confirms the terms before the owner puts them in force, and any
  later change by the owner needs a fresh confirmation;
- deliverables can't be added, rewritten or left outstanding behind completion;
- submitted work is answered before either party can terminate; either party
  may terminate, the other is told, and terminations show on both records;
- awards only to providers in good standing; a winner keeps access to its job;
- re-verification doesn't freeze a live transaction;
- the tender's commercial terms carry into the agreement;
- an awarded requirement shows how its transaction stands;
- changes keep the schedule coherent."""
from datetime import timedelta

from app.models.enums import NotificationType, SubscriptionStatus, VerificationStatus
from app.models.notification import Notification
from app.models.service_provider import ServiceProviderProfile
from app.routers.agreements import kuwait_today
from tests.stage7_helpers import put_in_force
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award
from tests.test_stage8_15_review_moderation import _admin


def _v(c, pid):
    return {"If-Match": str(c.get(f"/projects/{pid}/agreement").json()["version"])}


def _mv(c, pid, mid):
    return {"If-Match": str(next(m for m in c.get(f"/projects/{pid}/agreement").json()["milestones"] if m["id"] == mid)["version"])}


def _awarded(db, tag):
    owner = _account(db, "owner", f"o-{tag}@example.com")
    sp = _account(db, "service_provider", f"s-{tag}@example.com")
    pid = _tender(owner)
    _award(owner, sp, pid)
    return owner, sp, pid, f"/projects/{pid}/agreement"


def _types(db, user_id):
    return {n.type for n in db.query(Notification).filter(Notification.user_id == user_id)}


def test_no_work_until_the_agreement_is_in_force_and_effective(db):
    owner, sp, pid, base = _awarded(db, "force")
    # Being prepared: nothing about the work can be recorded.
    r = sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid))
    assert r.status_code == 400 and "isn't in force" in r.json()["detail"]
    assert sp.post(f"{base}/completion/submit", json={}, headers=_v(sp, pid)).status_code == 400
    # The effective date can't precede the award.
    yesterday = (kuwait_today() - timedelta(days=1)).isoformat()
    assert owner.patch(base, json={"effective_date": yesterday}, headers=_v(owner, pid)).status_code == 400
    # In force from a future date: still no start before that date.
    put_in_force(owner, sp, pid, effective=kuwait_today() + timedelta(days=5))
    r = sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid))
    assert r.status_code == 400 and "takes effect on" in r.json()["detail"]
    ag = owner.get(base).json()
    assert ag["status"] == "active" and ag["work_started_at"] is None and ag["activated_at"]


def test_the_provider_confirms_the_terms_and_owner_changes_need_a_fresh_confirmation(db):
    owner, sp, pid, base = _awarded(db, "confirm")
    assert sp.post(f"{base}/confirm", headers=_v(sp, pid)).status_code == 400  # nothing to confirm yet: no effective date
    owner.patch(base, json={"effective_date": kuwait_today().isoformat()}, headers=_v(owner, pid))
    r = owner.post(f"{base}/activate", headers=_v(owner, pid))
    assert r.status_code == 400 and "hasn't confirmed" in r.json()["detail"]
    assert owner.post(f"{base}/confirm", headers=_v(owner, pid)).status_code == 403  # only the provider confirms
    assert sp.post(f"{base}/confirm", headers=_v(sp, pid)).status_code == 200
    owner_id = owner.get("/auth/me").json()["id"]
    assert NotificationType.agreement_terms_confirmed in _types(db, owner_id)
    # The owner then adds a deliverable: the confirmation no longer stands.
    owner.post(f"{base}/milestones", json={"title": "Handover file"}, headers=_v(owner, pid))
    assert owner.get(base).json()["provider_confirmed_at"] is None
    assert owner.post(f"{base}/activate", headers=_v(owner, pid)).status_code == 400
    # A reference-only edit keeps the effective date (partial update).
    owner.patch(base, json={"reference": "WO-1"}, headers=_v(owner, pid))
    assert owner.get(base).json()["effective_date"] == kuwait_today().isoformat()
    sp.post(f"{base}/confirm", headers=_v(sp, pid))
    assert owner.post(f"{base}/activate", headers=_v(owner, pid)).status_code == 200
    sp_id = sp.get("/auth/me").json()["id"]
    assert NotificationType.agreement_in_force in _types(db, sp_id)
    timeline = [e["kind"] for e in owner.get(base).json()["timeline"]]
    assert timeline.index("terms_confirmed") < timeline.index("in_force")


def test_deliverables_are_fixed_and_completion_rechecks_them(db):
    owner, sp, pid, base = _awarded(db, "deliv")
    owner.patch(base, json={"effective_date": kuwait_today().isoformat()}, headers=_v(owner, pid))
    owner.post(f"{base}/milestones", json={"title": "Roof membrane"}, headers=_v(owner, pid))
    sp.post(f"{base}/confirm", headers=_v(sp, pid))
    owner.post(f"{base}/activate", headers=_v(owner, pid))
    mid = owner.get(base).json()["milestones"][0]["id"]
    # In force: no new deliverables, no rewriting.
    assert owner.post(f"{base}/milestones", json={"title": "Added later"}, headers=_v(owner, pid)).status_code == 400
    assert owner.patch(f"{base}/milestones/{mid}", json={"title": "Renamed"}, headers=_mv(owner, pid, mid)).status_code == 400
    sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid))
    # Completion can't be submitted with the deliverable outstanding.
    assert sp.post(f"{base}/completion/submit", json={}, headers=_v(sp, pid)).status_code == 400
    sp.post(f"{base}/milestones/{mid}/deliver", json={}, headers=_mv(sp, pid, mid))
    owner.post(f"{base}/milestones/{mid}/accept", json={}, headers=_mv(owner, pid, mid))
    assert sp.post(f"{base}/completion/submit", json={}, headers=_v(sp, pid)).status_code == 200
    r = owner.post(f"{base}/completion/accept", json={}, headers=_v(owner, pid))
    assert r.status_code == 200 and r.json()["status"] == "completed" and r.json()["outstanding_deliverables"] == 0


def test_submitted_work_is_answered_before_termination_and_terminations_show(db):
    owner, sp, pid, base = _awarded(db, "term")
    put_in_force(owner, sp, pid)
    sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid))
    sp.post(f"{base}/completion/submit", json={}, headers=_v(sp, pid))
    r = owner.post(f"{base}/terminate", json={"reason": "Not satisfied"}, headers=_v(owner, pid))
    assert r.status_code == 409 and "accepts it or returns it" in r.json()["detail"]
    # Returned for correction, then the provider walks away: either party may terminate.
    owner.post(f"{base}/completion/return", json={"note": "Drains blocked"}, headers=_v(owner, pid))
    r = sp.post(f"{base}/terminate", json={"reason": "Owner stopped site access"}, headers=_v(sp, pid))
    assert r.status_code == 200 and r.json()["terminated_party"] == "provider"
    owner_id, sp_id = owner.get("/auth/me").json()["id"], sp.get("/auth/me").json()["id"]
    assert NotificationType.agreement_terminated in _types(db, owner_id)
    assert sp.get("/service-provider/reputation").json()["terminated_transactions"] == 1
    assert owner.get("/owner/reputation").json()["terminated_transactions"] == 1
    assert owner.get(f"/projects/{pid}").json()["transaction_status"] == "terminated"


def test_award_requires_a_provider_in_good_standing(db):
    admin = _admin(db)
    owner = _account(db, "owner", "o-standing@example.com")
    sp = _account(db, "service_provider", "s-standing@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    sid = sp.get("/auth/me").json()["id"]
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    admin.post(f"/admin/service-providers/{sid}/suspend", json={"suspended": True})
    r = owner.post(f"/owner/projects/{pid}/offers/{oid}/approve")
    assert r.status_code == 409 and "good standing" in r.json()["detail"]
    admin.post(f"/admin/service-providers/{sid}/suspend", json={"suspended": False})
    assert owner.post(f"/owner/projects/{pid}/offers/{oid}/approve").status_code == 200


def test_the_winner_keeps_its_job_through_a_lapsed_subscription_and_a_re_review(db):
    owner, sp, pid, base = _awarded(db, "keep")
    put_in_force(owner, sp, pid)
    cp = db.get(ServiceProviderProfile, sp.get("/auth/me").json()["id"])
    cp.payment_override_active, cp.subscription_status = False, SubscriptionStatus.past_due
    db.commit()
    assert sp.get(f"/projects/{pid}").status_code == 200  # scope, address, drawings of its own job
    # Its documents go back for correction: the live transaction carries on.
    cp.verification_status = VerificationStatus.changes_requested
    db.commit()
    assert sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid)).status_code == 200
    # A suspension still stops it.
    cp.is_suspended = True
    db.commit()
    assert sp.get(base).status_code == 404
    assert sp.post(f"{base}/progress", json={"action": "update", "note": "x"}).status_code == 404


def test_commercial_terms_carry_into_the_agreement(db):
    owner = _account(db, "owner", "o-terms@example.com")
    sp = _account(db, "service_provider", "s-terms@example.com")
    pid = owner.post("/projects", data={"title": "Terrace", "address": "Salwa", "description": "Tiling.", "bid_deadline": (kuwait_today() + timedelta(days=10)).isoformat() + "T12:00:00+03:00"}).json()["id"]
    owner.put(f"/projects/{pid}/tender-rules", json={"commercial_conditions": {
        "payment_stages": [{"milestone": "On mobilisation", "percent": "30"}, {"milestone": "On completion", "percent": "70"}],
        "retention_percent": "5", "retention_months": 12, "warranty_months": 24}})
    owner.post(f"/owner/projects/{pid}/publish")
    sp.post(f"/projects/{pid}/participate")
    sp.post(f"/projects/{pid}/offers", json={"amount": "1000.000"})
    owner.post(f"/owner/projects/{pid}/close")
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{oid}/approve").status_code == 200
    base = f"/projects/{pid}/agreement"
    terms = owner.get(base).json()["commercial_terms"]
    assert [(s["milestone"], s["amount"]) for s in terms["payment_stages"]] == [("On mobilisation", "300.000"), ("On completion", "700.000")]
    assert terms["retention_amount"] == "50.000" and terms["warranty_until"] is None
    put_in_force(owner, sp, pid)
    sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid))
    sp.post(f"{base}/completion/submit", json={}, headers=_v(sp, pid))
    owner.post(f"{base}/completion/accept", json={}, headers=_v(owner, pid))
    terms = owner.get(base).json()["commercial_terms"]
    assert terms["warranty_until"] and terms["retention_release_on"] and terms["warranty_until"] > terms["retention_release_on"]
    assert owner.get(f"/projects/{pid}").json()["transaction_status"] == "completed"


def test_changes_keep_the_schedule_coherent(db):
    owner, sp, pid, base = _awarded(db, "sched")
    owner.patch(base, json={"effective_date": kuwait_today().isoformat()}, headers=_v(owner, pid))
    owner.post(f"{base}/milestones", json={"title": "Phase 1", "due_date": (kuwait_today() + timedelta(days=10)).isoformat()}, headers=_v(owner, pid))
    sp.post(f"{base}/confirm", headers=_v(sp, pid))
    owner.post(f"{base}/activate", headers=_v(owner, pid))
    mid = owner.get(base).json()["milestones"][0]["id"]
    past = (kuwait_today() - timedelta(days=1)).isoformat()
    r = owner.post(f"{base}/variations", json={"description": "Earlier finish", "completion_date": past}, headers=_v(owner, pid))
    assert r.status_code == 400  # before the award, and in the past
    finish = kuwait_today() + timedelta(days=20)
    r = owner.post(f"{base}/variations", json={"description": "Move phase 1", "completion_date": finish.isoformat(), "milestone_id": mid,
                                                "milestone_due_date": (finish + timedelta(days=5)).isoformat()}, headers=_v(owner, pid))
    assert r.status_code == 400 and "due after the work's completion" in r.json()["detail"]
    r = owner.post(f"{base}/variations", json={"description": "Move phase 1", "completion_date": finish.isoformat(), "milestone_id": mid,
                                                "milestone_due_date": (finish - timedelta(days=5)).isoformat()}, headers=_v(owner, pid))
    assert r.status_code == 200

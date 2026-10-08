"""Stage 9.3: an admin follows one requirement through its whole life --
open with no offers, competing offers (and the version each priced), an
amendment, the award, the transaction it started and its history, the
completed or ended outcome -- from the authoritative records, never a stale
"open". Admin actions keep to the lifecycle; nobody else reaches any of it."""
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.project import Project
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage7_10_completion import _v
from tests.test_stage8_15_review_moderation import _admin


def _detail(admin, pid):
    r = admin.get(f"/admin/projects/{pid}")
    assert r.status_code == 200
    return r.json()


def test_an_admin_follows_a_requirement_through_its_life(db):
    admin = _admin(db)
    owner = _account(db, "owner", "owner@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in "abc")

    # A. Open, no offers.
    pid = _tender(owner, title="Tower maintenance", sealed=True)
    d = _detail(admin, pid)
    assert (d["project"]["status"], d["offers"], d["award"], d["transaction"]) == ("open", [], None, None)
    assert d["version"] == {"material_revision": 0, "amendments": 0}

    # B. Three offers on a sealed tender: the admin sees them (platform oversight); the owner still can't.
    for p in (a, b, c):
        _submitted(p, pid)
    d = _detail(admin, pid)
    assert len(d["offers"]) == 3 and all(o["based_on_material_revision"] == 0 and o["submitted_at"] for o in d["offers"])
    assert [o["service_provider_id"] for o in owner.get(f"/owner/projects/{pid}/offers").json()] == [None] * 3

    # G. A material amendment: the version moves on; the offers stay on the version they priced.
    assert owner.patch(f"/projects/{pid}", json={"description": "Two towers, not one."}).status_code == 200
    d = _detail(admin, pid)
    assert d["version"]["material_revision"] == 1 and d["version"]["amendments"] >= 1
    assert {o["based_on_material_revision"] for o in d["offers"]} == {0}
    assert len(admin.get(f"/projects/{pid}/amendments").json()) == d["version"]["amendments"]

    # C. Closed at its deadline -- shown closed straight away, never "open" -- then awarded to A.
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    assert _detail(admin, pid)["project"]["status"] in ("closed", "under_evaluation")
    win = a.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{win}/approve", json={"acknowledge_earlier_version": True}).status_code == 200
    d = _detail(admin, pid)
    assert d["project"]["status"] == "awarded"
    assert (d["award"]["offer_id"], d["award"]["service_provider_id"], d["award"]["offer_priced_on"]) == (win, a.get("/auth/me").json()["id"], 0)
    assert d["transaction"]["status"] == "preparing"
    assert {o["id"]: o["status"] for o in d["offers"]}[win] == "approved"

    # H. Admin actions keep to the lifecycle: no editing a decided requirement, no deleting the winning offer.
    assert admin.patch(f"/admin/projects/{pid}", json={"title": "Changed"}).status_code == 400
    assert admin.delete(f"/admin/offers/{win}").status_code == 400
    assert _detail(admin, pid)["project"]["title"] == "Tower maintenance"

    # D. Execution: the transaction's own history is readable to the admin.
    base = f"/projects/{pid}/agreement"
    owner.patch(base, json={"effective_date": (date.today() + timedelta(days=1)).isoformat()}, headers=_v(owner, pid))
    assert owner.post(f"{base}/activate", headers=_v(owner, pid)).status_code == 200
    assert a.post(f"{base}/start-work", json={}, headers=_v(a, pid)).status_code == 200
    assert _detail(admin, pid)["transaction"]["status"] == "active"
    kinds = [e["kind"] for e in admin.get(base).json()["timeline"]]
    assert kinds[0] == "awarded" and "started" in kinds
    assert admin.post(f"{base}/completion/submit", json={}, headers=_v(admin, pid)).status_code in (403, 404)  # read-only

    # E. Completed: shown as the outcome, not as an active transaction.
    assert a.post(f"{base}/completion/submit", json={}, headers=_v(a, pid)).status_code == 200
    assert _detail(admin, pid)["transaction"]["completion_status"] == "submitted"
    assert owner.post(f"{base}/completion/accept", json={}, headers=_v(owner, pid)).status_code == 200
    t = _detail(admin, pid)["transaction"]
    assert t["status"] == "completed" and t["completed_at"]

    # F. Cancelled and expired requirements are shown as they are.
    p2 = _tender(owner, title="Cancelled")
    owner.post(f"/owner/projects/{p2}/cancel", json={"reason": "other"})
    p3 = _tender(owner, title="Lapsed")
    db.get(Project, p3).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    listed = {p["id"]: p["status"] for p in admin.get("/admin/projects").json()}
    assert (listed[p2], listed[p3]) == ("canceled", "expired")
    assert _detail(admin, p2)["award"] is None and _detail(admin, p2)["transaction"] is None

    # Only admins.
    for client in (owner, a):
        assert client.get(f"/admin/projects/{pid}").status_code == 403
        assert client.get("/admin/projects").status_code == 403
    assert TestClient(app).get(f"/admin/projects/{pid}").status_code == 401

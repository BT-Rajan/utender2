"""Stage 4.8: a provider saves opportunities to come back to -- only ones
they can discover, once each, shared by their organization -- and the saved
list shows each as it stands now, never making anything look available that
isn't, and never more than the provider may see."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.enums import UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.saved_opportunity import SavedOpportunity
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User

needs_mysql = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs real row locking (MySQL)")


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _account(db, role, email, organization=None, joining=False, approve=True):
    c = TestClient(app)
    uid = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role}).json()["id"]
    if not joining:
        c.put("/account/stakeholder", json={"type": "organization", "legal_name": organization, "authorized": True} if organization else {"type": "individual"})
    if approve and not joining:
        model = OwnerProfile if role == "owner" else ServiceProviderProfile
        p = db.get(model, uid)
        p.verification_status = VerificationStatus.approved
        if role == "service_provider":
            p.company_name = email.split("@")[0]
            p.payment_override_active = True
        db.commit()
    return c


def _publish(owner, title, days=10, **extra):
    return owner.post("/projects", data={"title": title, "address": "Plot 1", "description": f"{title}: work as described.", "bid_deadline": _when(days), "status": "open", **extra}).json()["id"]


def _saved(client):
    r = client.get("/service-provider/saved")
    assert r.status_code == 200, r.text
    return r.json()


def test_save_see_unsave_save_again(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pids = [_publish(owner, f"Job {i:02}", days=5 + i) for i in range(20)]
    # A week of browsing: save the interesting ones (from a search), keep browsing.
    found = [p["id"] for p in sp.get("/service-provider/feed", params={"search": "Job 1", "sort": "deadline"}).json()["items"]]
    for pid in found[:4] + pids[:2]:
        assert sp.put(f"/service-provider/saved/{pid}").json() == {"project_id": pid, "saved": True}
    # Saving again, repeatedly: still one each.
    for _ in range(3):
        sp.put(f"/service-provider/saved/{pids[0]}")
    assert db.query(SavedOpportunity).count() == 6
    # The feed and the requirement say it's saved.
    feed = {p["id"]: p["saved"] for p in sp.get("/service-provider/feed", params={"limit": 50}).json()["items"]}
    assert feed[pids[0]] is True and feed[pids[5]] is False
    assert sp.get(f"/projects/{pids[0]}").json()["saved"] is True
    # The saved list: the same cards, closing soonest first, all open now.
    saved = _saved(sp)
    assert [s["id"] for s in saved] == sorted({*found[:4], *pids[:2]}, key=lambda i: pids.index(i))
    assert {s["availability"] for s in saved} == {"open"} and saved[0]["title"] == "Job 00" and saved[0]["summary"]
    # Open one from there: the requirement itself.
    assert sp.get(f"/projects/{saved[0]['id']}").json()["title"] == "Job 00"
    # Remove what's no longer of interest -- twice is fine -- and save it again.
    assert sp.delete(f"/service-provider/saved/{pids[0]}").json()["saved"] is False
    assert sp.delete(f"/service-provider/saved/{pids[0]}").status_code == 200
    assert pids[0] not in [s["id"] for s in _saved(sp)]
    sp.put(f"/service-provider/saved/{pids[0]}")
    assert db.query(SavedOpportunity).filter_by(project_id=pids[0]).count() == 1


def test_only_what_the_provider_can_discover(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    unverified = _account(db, "service_provider", "new@example.com", approve=False)
    other_owner = _account(db, "owner", "other@example.com")
    draft = owner.post("/projects", data={"title": "Draft", "address": "x", "bid_deadline": _when(9)}).json()["id"]
    restricted = owner.post("/projects", data={"title": "Orgs only", "address": "x", "description": "x", "bid_deadline": _when(9)}).json()["id"]
    owner.put(f"/projects/{restricted}/eligibility", json={"provider_type": "organization"})
    owner.post(f"/owner/projects/{restricted}/publish")
    ended = _publish(owner, "Ended")
    owner.post(f"/owner/projects/{ended}/cancel", json={"reason": "not_needed"})
    open_pid = _publish(owner, "Open")
    for pid in (draft, restricted, ended, "no-such-id"):
        assert sp.put(f"/service-provider/saved/{pid}").status_code == 404, pid
    assert unverified.put(f"/service-provider/saved/{open_pid}").status_code == 403
    assert other_owner.put(f"/service-provider/saved/{open_pid}").status_code == 403  # not a provider
    assert other_owner.get("/service-provider/saved").status_code == 403
    assert db.query(SavedOpportunity).count() == 0


def test_saved_items_follow_the_requirement_without_false_availability(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="A"))
    db.commit()
    admin = TestClient(app)
    admin.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    paused, hidden, extended, amended, expired, canceled, closed = (_publish(owner, t) for t in ("Paused", "Hidden", "Extended", "Amended", "Expired", "Canceled", "Closed"))
    for pid in (paused, hidden, extended, amended, expired, canceled, closed):
        sp.put(f"/service-provider/saved/{pid}")
    sp.post(f"/projects/{closed}/offers", json={"amount": "900"})
    owner.post(f"/owner/projects/{paused}/pause", json={"reason": "Waiting for the permit."})
    admin.post(f"/admin/projects/{hidden}/suspend", json={"suspended": True})
    v = owner.get(f"/projects/{extended}").json()["version"]
    later = _when(30)
    owner.patch(f"/projects/{extended}", json={"bid_deadline": later}, headers={"If-Match": str(v)})
    v = owner.get(f"/projects/{amended}").json()["version"]
    owner.patch(f"/projects/{amended}", json={"description": "Amended: bigger scope."}, headers={"If-Match": str(v)})
    db.get(Project, expired).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.post(f"/owner/projects/{canceled}/cancel", json={"reason": "postponed"})
    owner.post(f"/owner/projects/{closed}/close")

    saved = {s["id"]: s for s in _saved(sp)}
    assert len(saved) == 7  # nothing silently dropped
    assert (saved[paused]["availability"], saved[paused]["paused_at"] is not None) == ("paused", True)
    assert saved[extended]["availability"] == "open" and saved[extended]["bid_deadline"] == later  # same requirement, current deadline
    assert saved[amended]["summary"].startswith("Amended")  # the current requirement
    assert (saved[expired]["availability"], saved[expired]["status"]) == ("ended", "expired")
    assert (saved[canceled]["availability"], saved[canceled]["status"], saved[canceled]["closure_reason"]) == ("ended", "canceled", "postponed")
    assert saved[canceled]["summary"] is None  # ended, never took part: the listing only
    assert saved[closed]["availability"] == "ended" and saved[closed]["my_offer_status"] == "submitted"
    # Hidden by U-Tender: that it's unavailable -- nothing about it.
    assert saved[hidden]["availability"] == "unavailable" and saved[hidden]["title"] == "" and saved[hidden]["summary"] is None
    # Order: what's still open first, then what has ended, then the unavailable.
    order = [saved[i]["availability"] for i in [s["id"] for s in _saved(sp)]]
    assert order == sorted(order, key=["open", "paused", "ended", "unavailable"].index) or order[:3].count("ended") == 0
    # Nothing it shows reopens anything: offering on an ended saved one is refused as before.
    assert sp.post(f"/projects/{canceled}/offers", json={"amount": "1"}).status_code == 400
    # A deleted requirement takes its saved rows with it.
    draft = owner.post("/projects", data={"title": "Temp", "address": "x", "bid_deadline": _when(5)}).json()["id"]
    db.add(SavedOpportunity(project_id=draft, service_provider_id=sp.get("/auth/me").json()["id"]))
    db.commit()
    assert admin.delete(f"/admin/projects/{draft}").status_code == 204
    db.expire_all()
    assert db.query(SavedOpportunity).filter_by(project_id=draft).count() == 0


def test_an_organization_shares_one_list(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    rival = _account(db, "service_provider", "rival@example.com")
    pid = _publish(owner, "Villa rewiring")
    eng.put(f"/service-provider/saved/{pid}")
    boss.put(f"/service-provider/saved/{pid}")  # the same organization: still one
    assert [s["id"] for s in _saved(boss)] == [pid] and db.query(SavedOpportunity).count() == 1
    assert _saved(rival) == []
    rival.delete(f"/service-provider/saved/{pid}")  # can't remove someone else's
    assert [s["id"] for s in _saved(eng)] == [pid]


@needs_mysql
def test_simultaneous_saves_and_unsaves(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner, "Villa rewiring")
    clients = [sp] + [TestClient(app) for _ in range(3)]
    for c in clients[1:]:
        c.post("/auth/login", json={"email": "noor@example.com", "password": "password123"})
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: c.put(f"/service-provider/saved/{pid}"), clients))
    assert all(r.status_code == 200 for r in results) and db.query(SavedOpportunity).count() == 1
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda ic: ic[1].put(f"/service-provider/saved/{pid}") if ic[0] % 2 else ic[1].delete(f"/service-provider/saved/{pid}"), enumerate(clients)))
    assert all(r.status_code == 200 for r in results)
    db.expire_all()
    assert db.query(SavedOpportunity).count() in (0, 1)  # one consistent outcome, never a duplicate

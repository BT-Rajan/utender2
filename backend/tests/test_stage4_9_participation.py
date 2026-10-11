"""Stage 4.9: a provider decides to take part -- from evaluating an
opportunity to preparing an offer -- only when every condition holds now,
judged by the server; told why when not; recorded once; flagged when the
requirement changes after they decided. Offering is deciding."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.enums import UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.participation import Participation
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from tests._verified import verify_email

needs_mysql = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs real row locking (MySQL)")


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _account(db, role, email, organization=None, joining=False, approve=True, paid=True):
    c = TestClient(app)
    uid = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role}).json()["id"]
    if joining:
        verify_email(email)  # a colleague accepting an invitation needs a verified email
    if not joining:
        c.put("/account/stakeholder", json={"type": "organization", "legal_name": organization, "authorized": True} if organization else {"type": "individual"})
    if approve and not joining:
        model = OwnerProfile if role == "owner" else ServiceProviderProfile
        p = db.get(model, uid)
        p.verification_status = VerificationStatus.approved
        if role == "service_provider":
            p.company_name = email.split("@")[0]
            p.payment_override_active = paid
        db.commit()
    return c


def _publish(owner, title="Villa rewiring", days=10):
    return owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Rewire a villa: 40 points.", "bid_deadline": _when(days), "status": "open"}).json()["id"]


def _admin(db):
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="A"))
    db.commit()
    a = TestClient(app)
    a.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    return a


def test_decide_once_then_offer(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    assert sp.get(f"/projects/{pid}").json()["participation"]["started"] is False
    # 1. Eligible, open: proceeds. 8. Twice: still one decision.
    r = sp.post(f"/projects/{pid}/participate")
    assert r.status_code == 200 and r.json()["status"] == "can_participate" and r.json()["started"] is True and r.json()["seen_material_revision"] == 0
    assert sp.post(f"/projects/{pid}/participate").status_code == 200
    assert db.query(Participation).count() == 1
    # Shown on the requirement and among what they're preparing; nothing sent to the owner.
    assert sp.get(f"/projects/{pid}").json()["participation"]["started"] is True
    assert [p["project_id"] for p in sp.get("/service-provider/preparing").json()] == [pid]
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    # 9. Coming back finds where they left off; the offer itself goes through the existing route.
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 200
    assert db.query(Participation).count() == 1 and sp.get("/service-provider/preparing").json() == []


def test_offering_is_deciding(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    sp.post(f"/projects/{pid}/offers", json={"amount": "900"})
    assert db.query(Participation).count() == 1 and sp.get(f"/projects/{pid}").json()["participation"]["started"] is True


def test_who_cannot_take_part_and_why(db):
    owner = _account(db, "owner", "owner@example.com")
    pid = _publish(owner)
    # 2. Not eligible: refused with the reason.
    restricted = owner.post("/projects", data={"title": "Orgs only", "address": "x", "description": "HV works.", "bid_deadline": _when(9)}).json()["id"]
    owner.put(f"/projects/{restricted}/eligibility", json={"provider_type": "organization"})
    owner.post(f"/owner/projects/{restricted}/publish")
    sp = _account(db, "service_provider", "noor@example.com")
    r = sp.post(f"/projects/{restricted}/participate")
    assert r.status_code == 403 and "organization" in r.json()["detail"]
    # 3. Not verified; verified without marketplace access.
    unverified = _account(db, "service_provider", "new@example.com", approve=False)
    r = unverified.post(f"/projects/{pid}/participate")
    assert r.status_code == 403 and "verification" in r.json()["detail"]
    unpaid = _account(db, "service_provider", "free@example.com", paid=False)
    r = unpaid.post(f"/projects/{pid}/participate")
    assert r.status_code == 403 and "marketplace access" in r.json()["detail"]
    # 4. Invited to an organization but not a member: acts for no one.
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    later = _account(db, "service_provider", "later@gulf.example", joining=True)
    boss.post("/account/organization/invitations", json={"email": "later@gulf.example"})
    assert later.post(f"/projects/{pid}/participate").status_code == 403
    # Owners and drafts: no.
    assert owner.post(f"/projects/{pid}/participate").status_code == 403
    draft = owner.post("/projects", data={"title": "Draft", "address": "x", "bid_deadline": _when(9)}).json()["id"]
    assert sp.post(f"/projects/{draft}/participate").status_code == 404
    assert db.query(Participation).count() == 0


def test_the_requirement_state_decides_at_the_moment_of_asking(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    paused, hidden, expiring, closing = (_publish(owner, t) for t in ("Paused", "Hidden", "Expiring", "Closing"))
    # The provider has each open on screen; then, before they click:
    for pid in (paused, hidden, expiring, closing):
        assert sp.get(f"/projects/{pid}").json()["participation"]["status"] == "can_participate"
    owner.post(f"/owner/projects/{paused}/pause", json={"reason": "Waiting for the permit."})
    admin.post(f"/admin/projects/{hidden}/suspend", json={"suspended": True})
    db.get(Project, expiring).bid_deadline = datetime.utcnow() - timedelta(seconds=1)  # 7. the deadline passes
    db.commit()
    owner.post(f"/owner/projects/{closing}/cancel", json={"reason": "not_needed"})  # 11. the owner ends it
    # 5/6/7/11. The stale page doesn't matter: the server refuses, saying why.
    expected = {paused: "paused by its owner", hidden: "temporarily unavailable", expiring: "no longer accepting offers", closing: "no longer accepting offers"}
    for pid, words in expected.items():
        r = sp.post(f"/projects/{pid}/participate")
        assert r.status_code == 400 and words in r.json()["detail"], (pid, r.json())
    assert db.query(Participation).count() == 0
    # Already decided before it ended: no longer among what they're preparing.
    open_pid = _publish(owner, "Open")
    sp.post(f"/projects/{open_pid}/participate")
    owner.post(f"/owner/projects/{open_pid}/cancel", json={"reason": "postponed"})
    assert sp.get("/service-provider/preparing").json() == []


def test_a_material_change_after_deciding_is_flagged_until_seen(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    sp.post(f"/projects/{pid}/participate")
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Rewire a villa: 40 points plus 6 outdoor."}, headers={"If-Match": str(v)})
    # 10. The provider sees the current requirement -- and that it changed after they decided.
    d = sp.get(f"/projects/{pid}").json()
    assert d["description"].endswith("6 outdoor.") and d["material_revision"] == 1 and d["participation"]["seen_material_revision"] == 0
    assert sp.get("/service-provider/preparing").json()[0]["changed_since"] is True
    # Proceeding again records that they've seen the current version.
    assert sp.post(f"/projects/{pid}/participate").json()["seen_material_revision"] == 1
    assert sp.get("/service-provider/preparing").json()[0]["changed_since"] is False


def test_an_organization_decides_once(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    pid = _publish(owner)
    assert eng.post(f"/projects/{pid}/participate").status_code == 200
    assert boss.get(f"/projects/{pid}").json()["participation"]["started"] is True  # the organization's decision
    boss.post(f"/projects/{pid}/participate")
    assert db.query(Participation).count() == 1


@needs_mysql
def test_simultaneous_decisions_make_one(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    clients = [sp] + [TestClient(app) for _ in range(3)]
    for c in clients[1:]:
        c.post("/auth/login", json={"email": "noor@example.com", "password": "password123"})
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: c.post(f"/projects/{pid}/participate"), clients))
    assert all(r.status_code == 200 for r in results)
    db.expire_all()
    assert db.query(Participation).count() == 1

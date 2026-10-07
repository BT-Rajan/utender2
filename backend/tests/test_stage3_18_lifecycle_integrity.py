"""Stage 3.18: the requirement lifecycle end to end -- every state has one
authoritative meaning, invalid transitions are refused server-side whoever
asks (owner, provider or admin), and what providers can do always matches it."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import UserRole, VerificationStatus
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.project_amendment import ProjectAmendment
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User

MYSQL = bool(os.environ.get("TEST_DATABASE_URL"))
needs_mysql = pytest.mark.skipif(not MYSQL, reason="needs real row locking (MySQL); SQLite ignores FOR UPDATE")
OWNER_ACTIONS = ("publish", "resume", "close", "start-evaluation", "no-award", "cancel", "close-externally")


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _verified(db, role: str, email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.company_name = email.split("@")[0]
        profile.payment_override_active = True
    db.commit()
    return c


def _admin(db) -> TestClient:
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="A"))
    db.commit()
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"}).status_code == 200
    return c


def _published(owner: TestClient, days: float = 10) -> str:
    r = owner.post("/projects", data={"title": "Kitchen refit", "address": "Salwa, block 5", "governorate": "hawalli", "description": "Strip out and refit a 12 m² kitchen.", "bid_deadline": _when(days), "status": "open"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _patch(owner, pid, body):
    v = owner.get(f"/projects/{pid}").json()["version"]
    return owner.patch(f"/projects/{pid}", json=body, headers={"If-Match": str(v)})


def _status(owner, pid):
    return owner.get(f"/projects/{pid}").json()["status"]


def test_the_stage3_journey(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    beta = _verified(db, "service_provider", "beta@example.com")

    # 1-2. Start (once, however often sent), save incomplete, come back: private throughout.
    start = {"title": "Kitchen refit", "address": "Salwa, block 5", "bid_deadline": _when(10), "creation_token": "start-1"}
    pid = owner.post("/projects", data=start).json()["id"]
    assert owner.post("/projects", data=start).json()["id"] == pid
    assert alpha.get(f"/projects/{pid}").status_code == 404 and all(p["id"] != pid for p in alpha.get("/service-provider/feed").json()["items"])
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 400
    assert _patch(owner, pid, {"description": "Strip out and refit a 12 m² kitchen."}).status_code == 200
    assert _status(owner, pid) == "draft"

    # 3-4. Publish; providers discover and respond.
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 400  # once
    assert any(p["id"] == pid for p in alpha.get("/service-provider/feed").json()["items"])
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 200

    # 5-6. Pause: nothing accepted, nothing lost; resume.
    owner.post(f"/owner/projects/{pid}/pause", json={"reason": "Waiting for the landlord."})
    assert beta.post(f"/projects/{pid}/offers", json={"amount": "800"}).status_code == 400
    assert alpha.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    assert owner.post(f"/owner/projects/{pid}/resume").status_code == 200
    assert beta.post(f"/projects/{pid}/offers", json={"amount": "800"}).status_code == 200

    # 7-10. Extend, correct, amend materially -- offers stay tied to what they priced.
    assert _patch(owner, pid, {"bid_deadline": _when(14)}).json()["material_revision"] == 0
    assert _patch(owner, pid, {"title": "Kitchen refit — Salwa"}).json()["material_revision"] == 0
    assert _patch(owner, pid, {"description": "Strip out and refit a 16 m² kitchen with an island."}).json()["material_revision"] == 1
    assert {o["based_on_material_revision"] for o in owner.get(f"/owner/projects/{pid}/offers").json()} == {0}
    assert alpha.get(f"/projects/{pid}/versions/0").json()["fields"]["description"] == "Strip out and refit a 12 m² kitchen."

    # 11. Close early: offers stop, both kept; 15. none suitable: terminal, nothing awarded.
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    assert beta.post(f"/projects/{pid}/offers", json={"amount": "700"}).status_code == 400
    assert owner.post(f"/owner/projects/{pid}/start-evaluation").status_code == 200
    assert db.query(AuditLog).filter(AuditLog.action == "project.start_evaluation").count() == 1
    assert owner.post(f"/owner/projects/{pid}/no-award").json()["status"] == "no_award"
    assert sorted(o.status.value for o in db.query(Offer).filter_by(project_id=pid)) == ["submitted", "submitted"]

    # 17. Nothing reopens it.
    for action in OWNER_ACTIONS:
        assert owner.post(f"/owner/projects/{pid}/{action}").status_code == 400, action
    assert _patch(owner, pid, {"bid_deadline": _when(30)}).status_code == 400
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "1"}).status_code == 400
    assert _status(owner, pid) == "no_award"


def _terminal(db, owner, alpha, how):
    pid = _published(owner)
    if how != "expired":
        offer = alpha.post(f"/projects/{pid}/offers", json={"amount": "900"}).json()["id"]
    if how == "canceled":
        owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "not_needed"})
    elif how == "closed_externally":
        owner.post(f"/owner/projects/{pid}/close-externally")
    elif how == "expired":
        db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    else:
        owner.post(f"/owner/projects/{pid}/close")
        if how == "no_award":
            owner.post(f"/owner/projects/{pid}/no-award")
        else:
            owner.post(f"/owner/projects/{pid}/offers/{offer}/approve")
    return pid


@pytest.mark.parametrize("how", ["canceled", "expired", "closed_externally", "no_award", "awarded"])
def test_terminal_outcomes_cannot_be_reopened_by_anyone(db, how):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    admin = _admin(db)
    pid = _terminal(db, owner, alpha, how)
    status = _status(owner, pid)
    assert status in ("canceled", "expired", "no_award", "awarded")
    for action in OWNER_ACTIONS:
        assert owner.post(f"/owner/projects/{pid}/{action}").status_code == 400, action
    assert owner.post(f"/owner/projects/{pid}/pause", json={"reason": "again"}).status_code == 400
    assert _patch(owner, pid, {"bid_deadline": _when(30)}).status_code == 400
    assert owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("x.pdf", b"%PDF", "application/pdf"))]).status_code == 400
    # Nor can an admin edit it back into an opportunity.
    assert admin.patch(f"/admin/projects/{pid}", json={"bid_deadline": _when(30)}).status_code == 400
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "1"}).status_code == 400
    assert _status(owner, pid) == status


def test_admin_suspension_stops_every_provider_action_and_both_sides_see_it(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    beta = _verified(db, "service_provider", "beta@example.com")
    admin = _admin(db)
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "900"})
    _patch(owner, pid, {"description": "A bigger kitchen."})  # alpha's offer now needs confirming
    assert admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True}).status_code == 200
    assert db.query(AuditLog).filter(AuditLog.action == "project.suspend").count() == 1

    assert beta.post(f"/projects/{pid}/offers", json={"amount": "800"}).status_code == 400
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "850"}).status_code == 400
    assert alpha.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    assert alpha.post(f"/projects/{pid}/offers/confirm").status_code == 400
    assert alpha.post(f"/projects/{pid}/clarifications", json={"question": "When?"}).status_code in (400, 404)
    assert db.query(Offer).one().status.value == "submitted"  # kept
    # The provider's own list says why it can't be opened; the owner's page says it is suspended.
    bid = next(b for b in alpha.get("/service-provider/my-bids").json() if b["project_id"] == pid)
    assert bid["project_suspended"] is True
    assert owner.get(f"/projects/{pid}").json()["is_suspended"] is True

    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": False})
    assert alpha.post(f"/projects/{pid}/offers/confirm").status_code == 200


def test_admin_corrections_follow_the_published_rules(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    admin = _admin(db)
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "900"})

    # A change to the scope is a recorded, announced amendment -- not a silent edit.
    r = admin.patch(f"/admin/projects/{pid}", json={"description": "Corrected scope: 14 m² kitchen."})
    assert r.status_code == 200
    a = db.query(ProjectAmendment).one()
    admin_id = db.query(User).filter(User.email == "admin@example.com").one().id
    assert a.material and a.created_by == admin_id and a.changes["description"]["from"] == "Strip out and refit a 12 m² kitchen."
    assert db.get(Project, pid).material_revision == 1 and db.query(Offer).one().based_on_material_revision == 0
    # The deadline: not into the past, not earlier once bids exist.
    assert admin.patch(f"/admin/projects/{pid}", json={"bid_deadline": _when(-1)}).status_code == 400
    assert admin.patch(f"/admin/projects/{pid}", json={"bid_deadline": _when(5)}).status_code == 400
    # A deadline that has just passed (status not yet synced) is never extended back open.
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert admin.patch(f"/admin/projects/{pid}", json={"bid_deadline": _when(20)}).status_code == 400
    assert _status(owner, pid) == "closed"
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "850"}).status_code == 400


@needs_mysql
def test_conflicting_endings_at_once_yield_exactly_one(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "900"})
    second = TestClient(app)
    assert second.post("/auth/login", json={"email": "owner@example.com", "password": "password123"}).status_code == 200
    calls = [(owner, "cancel", {"reason": "postponed"}), (second, "close-externally", {})]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda c: c[0].post(f"/owner/projects/{pid}/{c[1]}", json=c[2]), calls))
    assert sorted(r.status_code for r in results) == [200, 400], [(r.status_code, r.text[:80]) for r in results]
    db.expire_all()
    row = db.get(Project, pid)
    winner = next(r.json() for r in results if r.status_code == 200)
    assert (row.status.value, row.closure_reason) == (winner["status"], winner["closure_reason"])
    assert db.query(AuditLog).filter(AuditLog.action.in_(["project.cancel", "project.closed_externally"])).count() == 1

"""Stage 3.14: publishing turns a checked draft into a real opportunity in one
authoritative step -- and only then can providers find it, open it, see its
documents and respond."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile

pytestmark = pytest.mark.quality_gate

DEADLINE = (datetime.utcnow() + timedelta(days=14)).replace(microsecond=0).isoformat() + "Z"
SCOPE = "Build a 2.4 m block boundary wall (60 m) with RC columns every 3 m and one sliding gate; excavation and plaster both sides."
GOOD = {"title": "Boundary wall — plot 12", "address": "Sabah Al-Ahmad, block 3, plot 12", "governorate": "ahmadi", "area": "Sabah Al-Ahmad", "trade": "Masonry", "description": SCOPE, "bid_deadline": DEADLINE}


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


def test_draft_to_published_opportunity(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "wall@example.com")
    pid = owner.post("/projects", data=GOOD, files=[("drawings", ("wall-plan.pdf", b"%PDF-1 plan", "application/pdf"))]).json()["id"]

    # Before: checked, previewed, still invisible.
    assert owner.get(f"/projects/{pid}/quality").json()["ready"] is True
    assert owner.get(f"/projects/{pid}").json()["published_at"] is None
    assert sp.get(f"/projects/{pid}").status_code == 404 and all(p["id"] != pid for p in sp.get("/service-provider/feed").json())
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "5000"}).status_code == 400

    before = datetime.utcnow().replace(microsecond=0)
    r = owner.post(f"/owner/projects/{pid}/publish")
    assert r.status_code == 200 and r.json()["status"] == "open"
    published_at = datetime.fromisoformat(r.json()["published_at"].rstrip("Z"))
    assert before <= published_at <= datetime.utcnow() + timedelta(seconds=1)  # recorded by the server
    assert db.query(AuditLog).filter(AuditLog.action == "project.publish", AuditLog.target_id == pid).count() == 1

    # The provider: discovers it, opens it, reaches its documents, sees the deadline and rules, responds.
    assert any(p["id"] == pid for p in sp.get("/service-provider/feed", params={"sort": "newest"}).json())
    opened = sp.get(f"/projects/{pid}").json()
    assert opened["bid_deadline"] == DEADLINE and opened["response_requirements"] and opened["tender_rules"]["questions_open"] is True
    document = opened["drawings"][0]
    path = document["url"].split("://", 1)[-1].split("/", 1)[-1]
    assert sp.get("/" + path).content == b"%PDF-1 plan"
    assert sp.get(f"/projects/{pid}/eligibility").json()["eligible"] is True
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "5000.000", "timeline_estimate": "6 weeks"}).status_code == 200


def test_publication_is_guarded(db):
    owner = _verified(db, "owner", "owner@example.com")
    other = _verified(db, "owner", "other@example.com")
    sp = _verified(db, "service_provider", "wall@example.com")

    # An incomplete draft can't be published, and nothing changes.
    thin = owner.post("/projects", data={"title": "Wall", "address": "Ahmadi", "bid_deadline": DEADLINE}).json()["id"]
    assert owner.post(f"/owner/projects/{thin}/publish").status_code == 400
    row = db.get(Project, thin)
    assert (row.status.value, row.published_at) == ("draft", None) and sp.get(f"/projects/{thin}").status_code == 404

    # Nobody but the owner's side can publish.
    pid = owner.post("/projects", data=GOOD).json()["id"]
    assert other.post(f"/owner/projects/{pid}/publish").status_code == 404
    assert sp.post(f"/owner/projects/{pid}/publish").status_code == 403
    assert db.get(Project, pid).status.value == "draft"

    # Once only.
    first = owner.post(f"/owner/projects/{pid}/publish").json()["published_at"]
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 400
    assert owner.get(f"/projects/{pid}").json()["published_at"] == first
    assert db.query(AuditLog).filter(AuditLog.action == "project.publish", AuditLog.target_id == pid).count() == 1
    # The publication time can't be set from outside.
    version = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"published_at": "2020-01-01T00:00:00Z", "title": "Boundary wall — plot 12 (rev)"}, headers={"If-Match": str(version)})
    assert owner.get(f"/projects/{pid}").json()["published_at"] == first


def test_the_deadline_is_the_servers(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "wall@example.com")
    pid = owner.post("/projects", data=GOOD).json()["id"]
    owner.post(f"/owner/projects/{pid}/publish")
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "4800"}).status_code == 200
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    r = sp.post(f"/projects/{pid}/offers", json={"amount": "4700"})
    assert r.status_code == 400 and "closed" in r.json()["detail"]
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 400


def test_publish_now_from_the_start_form_is_the_same_step(db):
    owner = _verified(db, "owner", "owner@example.com")
    # Refused: nothing is left behind -- no stray draft, nothing half-published.
    r = owner.post("/projects", data={"title": "x", "address": "y", "bid_deadline": DEADLINE, "status": "open"})
    assert r.status_code == 400 and db.query(Project).count() == 0
    # A file that can't be stored fails the start without anything published.
    r = owner.post("/projects", data={**GOOD, "status": "open"}, files=[("drawings", ("evil.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 400 and db.query(Project).count() == 0
    # Accepted: published with its documents already in place, through the same transition.
    r = owner.post("/projects", data={**GOOD, "status": "open"}, files=[("drawings", ("plan.pdf", b"%PDF", "application/pdf"))])
    assert r.status_code == 201 and r.json()["status"] == "open" and r.json()["published_at"] and len(r.json()["drawings"]) == 1
    assert db.query(AuditLog).filter(AuditLog.action == "project.publish").count() == 1

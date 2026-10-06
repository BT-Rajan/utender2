"""Stage 3.2: a draft requirement's basic identity -- title, type of work,
location and description -- can be entered, saved and found again, while the
draft stays private and unpublished."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.project_amendment import ProjectAmendment
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat()


def _verified(db, role: str, email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.payment_override_active = True
    db.commit()
    return c


def test_owner_saves_basic_details_and_finds_them_again(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = owner.post("/projects", data={"title": "Villa work", "address": "Mishref", "bid_deadline": DEADLINE}).json()

    details = {
        "title": "Villa extension — ground floor majlis",
        "trade": "Construction",
        "address": "Mubarak Al-Kabeer — Mishref, Block 4, Street 12",
        "description": "Add a 40 m² majlis to an existing two-storey villa.",
    }
    r = owner.patch(f"/projects/{draft['id']}", json=details)
    assert r.status_code == 200, r.text

    # Leave and come back (a fresh session) -> the same information.
    again = TestClient(app)
    again.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    saved = again.get(f"/projects/{draft['id']}").json()
    assert {k: saved[k] for k in details} == details
    assert saved["status"] == "draft"

    # Saving a draft is not a published amendment.
    db.expire_all()
    assert db.get(Project, draft["id"]).revision == 1
    assert db.query(ProjectAmendment).filter(ProjectAmendment.project_id == draft["id"]).count() == 0

    # Location can't be blanked out.
    assert owner.patch(f"/projects/{draft['id']}", json={"address": "  "}).status_code == 400


def test_draft_details_stay_private(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = owner.post("/projects", data={"title": "Villa work", "address": "Mishref", "bid_deadline": DEADLINE}).json()
    owner.patch(f"/projects/{draft['id']}", json={"trade": "Construction"})

    sp = _verified(db, "service_provider", "sp@example.com")
    assert sp.get(f"/projects/{draft['id']}").status_code == 404
    assert draft["id"] not in [p["id"] for p in sp.get("/service-provider/feed").json()]

    other = _verified(db, "owner", "other@example.com")
    assert other.patch(f"/projects/{draft['id']}", json={"title": "Hijacked"}).status_code == 404


def test_editing_a_published_requirement_is_still_an_amendment(db):
    owner = _verified(db, "owner", "owner@example.com")
    project = owner.post("/projects", data={"title": "Villa work", "address": "Mishref", "bid_deadline": DEADLINE, "status": "open"}).json()
    r = owner.patch(f"/projects/{project['id']}", json={"address": "Mishref, Block 4"})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Project, project["id"]).revision == 2
    assert db.query(ProjectAmendment).filter(ProjectAmendment.project_id == project["id"]).count() == 1

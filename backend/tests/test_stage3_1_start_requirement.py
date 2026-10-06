"""Stage 3.1: an eligible owner starts a requirement.

Owner -> create requirement -> draft created -> belongs to the owner's
stakeholder (individual or organization) -> owner can return to it ->
service providers can't see it. Plus: starting never publishes by accident,
and a failed start leaves nothing behind."""
import io
import zipfile
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat()


def _owner(db, email: str, stakeholder: dict, approve: bool = True) -> tuple[TestClient, str]:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "Fahad", "role": "owner"})
    assert r.status_code == 201, r.text
    assert c.put("/account/stakeholder", json=stakeholder).status_code == 200
    user_id = r.json()["id"]
    if approve:
        db.get(OwnerProfile, user_id).verification_status = VerificationStatus.approved
        db.commit()
    return c, user_id


def _service_provider(db) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": "sp@example.com", "password": "password123", "full_name": "S", "role": "service_provider"})
    profile = db.get(ServiceProviderProfile, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    profile.payment_override_active = True  # fully eligible: can see every published project
    db.commit()
    return c


def _start(c: TestClient, **extra):
    data = {"title": "Villa extension, Mishref", "address": "Block 4, Mishref", "bid_deadline": DEADLINE}
    return c.post("/projects", data=data, **extra)


@pytest.mark.parametrize(
    "stakeholder",
    [{"type": "individual"}, {"type": "organization", "legal_name": "Al-Sabah Real Estate Co.", "authorized": True}],
    ids=["individual", "organization"],
)
def test_owner_starts_a_draft_that_only_they_can_see(db, stakeholder):
    owner, owner_id = _owner(db, "owner@example.com", stakeholder)
    sp = _service_provider(db)

    # No status sent: starting a requirement never publishes it.
    r = _start(owner)
    assert r.status_code == 201, r.text
    project = r.json()
    assert project["status"] == "draft"

    # It belongs to the owner's established stakeholder (and, for a business,
    # its organization) -- the identity Step 3 locks once verified.
    identity = owner.get("/account/identity").json()
    assert project["owner_id"] == identity["acting_as"]["stakeholder_id"] == owner_id
    if stakeholder["type"] == "organization":
        assert identity["acting_as"]["organization_id"] == identity["stakeholder"]["organization"]["id"]

    # The owner can come back to it later.
    assert owner.get(f"/projects/{project['id']}").status_code == 200
    assert project["id"] in [p["id"] for p in owner.get("/owner/projects").json()]

    # Service providers can't see or reach it.
    assert project["id"] not in [p["id"] for p in sp.get("/service-provider/feed").json()]
    assert sp.get(f"/projects/{project['id']}").status_code == 404

    # Nor can any other owner.
    other, _ = _owner(db, "other@example.com", {"type": "individual"})
    assert other.get(f"/projects/{project['id']}").status_code == 404


def test_only_an_eligible_owner_can_start(db):
    unverified, _ = _owner(db, "pending@example.com", {"type": "individual"}, approve=False)
    assert _start(unverified).status_code == 403
    assert db.query(Project).count() == 0


def test_a_failed_start_leaves_nothing_behind(db):
    owner, _ = _owner(db, "owner@example.com", {"type": "individual"})

    # A disallowed file type is refused before anything is created.
    r = _start(owner, files={"drawings": ("notes.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400
    assert db.query(Project).count() == 0

    # An archive refused mid-upload (after a valid drawing was processed)
    # removes the half-created project too.
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w") as z:
        for i in range(1001):
            z.writestr(f"sheet-{i}.pdf", b"")
    files = [("drawings", ("plan.pdf", b"%PDF-1.4", "application/pdf")), ("drawings", ("set.zip", bomb.getvalue(), "application/zip"))]
    r = _start(owner, files=files)
    assert r.status_code == 400
    db.expire_all()
    assert db.query(Project).count() == 0

    # A clean retry then creates exactly one draft.
    assert _start(owner).status_code == 201
    assert db.query(Project).count() == 1

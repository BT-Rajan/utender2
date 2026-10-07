"""Stage 3.11: a draft can be started, saved incomplete, left, resumed and
edited; discarded deliberately; never duplicated by a repeated start; never
overwritten by a stale page; and never visible to providers."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=21)).isoformat() + "Z"


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


def _login(email: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def test_start_save_leave_resume_edit_without_publishing(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = owner.post("/projects", data={"title": "Diwaniya renovation", "address": "Qortuba, block 2", "bid_deadline": DEADLINE}).json()
    pid = draft["id"]
    assert draft["status"] == "draft" and draft["updated_at"] and draft["version"] == 1
    # Only part of the information: a scope line, nothing else. Saved as is.
    r = owner.patch(f"/projects/{pid}", json={"description": "Replace ceiling and lighting."}, headers={"If-Match": str(draft["version"])})
    assert r.status_code == 200
    owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("ceiling.pdf", b"%PDF-1", "application/pdf"))])

    # Leave; come back later in a new session; the same draft is there.
    later = _login("owner@example.com")
    mine = later.get("/owner/projects").json()
    assert [(p["id"], p["status"]) for p in mine] == [(pid, "draft")]
    resumed = later.get(f"/projects/{pid}").json()
    assert resumed["description"] == "Replace ceiling and lighting." and resumed["drawings"][0]["file_name"] == "ceiling.pdf"

    # Continue editing (text and attachments), save again.
    r = later.patch(f"/projects/{pid}", json={"title": "Diwaniya renovation — ceiling & lighting"}, headers={"If-Match": str(resumed["version"])})
    assert r.status_code == 200
    later.delete(f"/projects/{pid}/drawings/{resumed['drawings'][0]['id']}")
    final = later.get(f"/projects/{pid}").json()
    assert final["title"].endswith("ceiling & lighting") and final["drawings"] == []
    # Leaving without publishing: still a private draft, still exactly one record.
    assert final["status"] == "draft" and db.query(Project).count() == 1


def test_a_repeated_start_does_not_create_a_second_draft(db):
    owner = _verified(db, "owner", "owner@example.com")
    form = {"title": "Garden wall", "address": "Salwa", "bid_deadline": DEADLINE, "creation_token": "0b6f8f9e-start-1"}
    first = owner.post("/projects", data=form).json()
    again = owner.post("/projects", data=form).json()  # double click / retry
    assert first["id"] == again["id"] and db.query(Project).count() == 1
    # A genuinely new start (new token) is a new draft.
    assert owner.post("/projects", data={**form, "creation_token": "0b6f8f9e-start-2"}).json()["id"] != first["id"]
    # The same token from a different owner is unrelated.
    other = _verified(db, "owner", "other@example.com")
    assert other.post("/projects", data=form).json()["id"] != first["id"]


def test_a_stale_page_cannot_overwrite_newer_work(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = owner.post("/projects", data={"title": "Kitchen", "address": "Mishref", "bid_deadline": DEADLINE}).json()
    pid, seen = draft["id"], str(draft["version"])
    # Two tabs opened on the same version; both save within the same second.
    tab_b = owner.patch(f"/projects/{pid}", json={"description": "Tab B: full scope"}, headers={"If-Match": seen})
    assert tab_b.status_code == 200 and tab_b.json()["version"] == draft["version"] + 1
    tab_a = owner.patch(f"/projects/{pid}", json={"description": "Tab A: old scope"}, headers={"If-Match": seen})
    assert tab_a.status_code == 409 and "Reload" in tab_a.json()["detail"]
    assert owner.get(f"/projects/{pid}").json()["description"] == "Tab B: full scope"
    # Every kind of draft save moves the version on, documents included.
    v = tab_b.json()["version"]
    r = owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("plan.pdf", b"%PDF", "application/pdf"))])
    assert r.json()["version"] == v + 1
    assert owner.put(f"/projects/{pid}/tender-rules", json={}, headers={"If-Match": str(v)}).status_code == 409


def test_a_draft_expires_at_its_offer_deadline(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sp@example.com")
    # A draft can't be started, or moved, onto a deadline that has passed.
    past = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
    assert owner.post("/projects", data={"title": "T", "address": "A", "bid_deadline": past}).status_code == 400
    pid = owner.post("/projects", data={"title": "Shade structure", "address": "Fintas", "bid_deadline": DEADLINE}).json()["id"]
    assert owner.patch(f"/projects/{pid}", json={"bid_deadline": past}).status_code == 400

    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    seen = owner.get(f"/projects/{pid}").json()
    assert seen["status"] == "expired"
    assert owner.patch(f"/projects/{pid}", json={"title": "x"}).status_code == 400  # read-only
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 400
    assert sp.get(f"/projects/{pid}").status_code == 404  # never published: still private
    assert [p["status"] for p in owner.get("/owner/projects").json()] == ["expired"]


def test_owner_discards_a_draft(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sp@example.com")
    keep = owner.post("/projects", data={"title": "Keep", "address": "A", "bid_deadline": DEADLINE}).json()["id"]
    drop = owner.post("/projects", data={"title": "Not going ahead", "address": "B", "bid_deadline": DEADLINE}).json()["id"]
    r = owner.post(f"/owner/projects/{drop}/discard")
    assert r.status_code == 200 and r.json()["discarded_at"] and r.json()["status"] == "draft"
    # No longer an active draft: not listed, not editable, not publishable.
    assert [p["id"] for p in owner.get("/owner/projects").json()] == [keep]
    assert owner.patch(f"/projects/{drop}", json={"title": "x"}).status_code == 409
    assert owner.post(f"/owner/projects/{drop}/publish").status_code == 400
    assert owner.post(f"/owner/projects/{drop}/discard").status_code == 400
    # Kept (soft) with an audit entry; still private.
    assert db.get(Project, drop) is not None
    assert db.query(AuditLog).filter(AuditLog.action == "project.discard_draft", AuditLog.target_id == drop).count() == 1
    assert sp.get(f"/projects/{drop}").status_code == 404
    # "Cancel" on a draft is the same discard (it must not become a canceled
    # tender, which providers can open).
    r = owner.post(f"/owner/projects/{keep}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "draft" and r.json()["discarded_at"]
    assert sp.get(f"/projects/{keep}").status_code == 404


def test_drafts_and_their_documents_are_private(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sp@example.com")
    intruder = _verified(db, "owner", "intruder@example.com")
    pid = owner.post(
        "/projects",
        data={"title": "Private", "address": "Exact plot 7", "bid_deadline": DEADLINE},
        files=[("drawings", ("plan.pdf", b"%PDF-1", "application/pdf"))],
    ).json()["id"]
    drawing_id = owner.get(f"/projects/{pid}").json()["drawings"][0]["id"]

    assert all(p["id"] != pid for p in sp.get("/service-provider/feed").json()["items"])
    for path in (f"/projects/{pid}", f"/projects/{pid}/drawings-zip", f"/projects/{pid}/drawings/history", f"/projects/{pid}/clarifications", f"/projects/{pid}/eligibility"):
        assert sp.get(path).status_code in (403, 404), path
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "100"}).status_code == 400

    # Another owner can't open, change, re-file or discard it.
    assert intruder.get(f"/projects/{pid}").status_code == 404
    assert intruder.patch(f"/projects/{pid}", json={"title": "Mine now"}).status_code == 404
    assert intruder.delete(f"/projects/{pid}/drawings/{drawing_id}").status_code == 404
    assert intruder.post(f"/owner/projects/{pid}/discard").status_code == 404
    assert owner.get(f"/projects/{pid}").json()["title"] == "Private"

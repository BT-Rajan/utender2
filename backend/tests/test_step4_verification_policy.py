"""Step 4: admin-defined verification policy -> checklist -> submission ->
review -> eligibility. No document type is named in application code; every
requirement below is created through the admin API, as an admin would."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.enums import MembershipRole, UserRole
from app.models.organization import OrganizationMembership
from app.models.user import User

PDF = {"file": ("doc.pdf", b"%PDF-1.4 test", "application/pdf")}

# (role, stakeholder) -> the requirement names that scope should produce.
POLICY = [
    ("Owner ID", "owner", "individual"),
    ("Owner company registration", "owner", "organization"),
    ("Owner proof of address", "owner", None),  # applies to both owner types
    ("Provider personal licence", "service_provider", "individual"),
    ("Provider company licence", "service_provider", "organization"),
]
EXPECTED = {
    ("owner", "individual"): {"Owner ID", "Owner proof of address"},
    ("owner", "organization"): {"Owner company registration", "Owner proof of address"},
    ("service_provider", "individual"): {"Provider personal licence"},
    ("service_provider", "organization"): {"Provider company licence"},
}
PREFIX = {"owner": "/owner", "service_provider": "/service-provider"}
ADMIN_PREFIX = {"owner": "/admin/review/owners", "service_provider": "/admin/review/service-providers"}


@pytest.fixture
def admin(db):
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"}).status_code == 200
    for name, role, scope in POLICY:
        r = c.post("/admin/requirements", json={"name": name, "applies_to": role, "applies_to_stakeholder": scope})
        assert r.status_code == 201, r.text
    return c


def _register(role: str, stakeholder: str, email: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "P", "role": role}).status_code == 201
    body = {"type": stakeholder}
    if stakeholder == "organization":
        body |= {"legal_name": "Acme Co", "authorized": True}
    assert c.put("/account/stakeholder", json=body).status_code == 200
    return c


def _checklist(c: TestClient, role: str) -> dict[str, dict]:
    return {d["requirement_name"]: d for d in c.get(f"{PREFIX[role]}/documents").json()}


def _admin_docs(admin: TestClient, role: str, user_id: str) -> dict[str, dict]:
    path = f"/admin/owners/{user_id}" if role == "owner" else f"/admin/service-providers/{user_id}"
    return {d["requirement_name"]: d for d in admin.get(path).json()["documents"]}


def _decide(admin, role, user_id, requirement_id, decision, **extra):
    if role == "owner":
        body = {"owner_id": user_id, "requirement_id": requirement_id, "decision": decision, **extra}
        return admin.post("/admin/review/owner-documents", json=body)
    body = {"service_provider_id": user_id, "requirement_id": requirement_id, "decision": decision, **extra}
    return admin.post("/admin/review/documents", json=body)


@pytest.mark.parametrize("role,stakeholder", list(EXPECTED))
def test_each_stakeholder_gets_its_configured_checklist_and_is_reviewed(admin, role, stakeholder):
    c = _register(role, stakeholder, f"{role}-{stakeholder}@example.com")
    user_id = c.get("/auth/me").json()["id"]
    assert set(_checklist(c, role)) == EXPECTED[(role, stakeholder)]
    assert {r["name"] for r in c.get(f"{PREFIX[role]}/requirements").json()} == EXPECTED[(role, stakeholder)]
    assert c.get("/account/identity").json()["stakeholder"]["status"]["eligible"] is False

    for doc in _checklist(c, role).values():
        assert c.post(f"{PREFIX[role]}/documents/{doc['requirement_id']}/upload", files=PDF).status_code == 200
    submit = {"company_name": "Acme Co"} if role == "service_provider" else None
    r = c.post(f"{PREFIX[role]}/submit-for-review", json=submit)
    assert r.status_code == 200, r.text
    assert r.json()["verification_state"] == "submitted"

    docs = _admin_docs(admin, role, user_id)
    assert set(docs) == EXPECTED[(role, stakeholder)]
    assert all(d["url"] for d in docs.values())  # admin can open every submitted document
    for d in docs.values():
        assert _decide(admin, role, user_id, d["requirement_id"], "approved").status_code == 200
    r = admin.post(f"{ADMIN_PREFIX[role]}/{user_id}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["verification_state"] == "approved"

    status = c.get("/account/identity").json()["stakeholder"]["status"]
    assert status["verified"] is True
    # Owners may now act; service providers still need an active subscription.
    assert status["eligible"] is (role == "owner")


def test_policy_change_applies_to_new_verifications_but_not_past_approvals(admin, db):
    approved = _register("owner", "individual", "approved@example.com")
    approved_id = approved.get("/auth/me").json()["id"]
    for doc in _checklist(approved, "owner").values():
        approved.post(f"/owner/documents/{doc['requirement_id']}/upload", files=PDF)
        _decide(admin, "owner", approved_id, doc["requirement_id"], "approved")
    approved.post("/owner/submit-for-review")
    assert admin.post(f"/admin/review/owners/{approved_id}/approve").status_code == 200

    # Admin adds a requirement and retires another.
    new_req = admin.post("/admin/requirements", json={"name": "Owner bank letter", "applies_to": "owner", "applies_to_stakeholder": "individual"}).json()
    retired = next(r for r in admin.get("/admin/requirements").json() if r["name"] == "Owner proof of address")
    admin.patch(f"/admin/requirements/{retired['id']}", json={"is_active": False})

    newcomer = _register("owner", "individual", "newcomer@example.com")
    assert set(_checklist(newcomer, "owner")) == {"Owner ID", "Owner bank letter"}

    # The earlier approval stands; the account isn't silently re-gated.
    status = approved.get("/account/identity").json()["stakeholder"]["status"]
    assert status["verification_status"] == "approved" and status["eligible"] is True
    # ...and it can't upload into a closed verification.
    r = approved.post(f"/owner/documents/{new_req['id']}/upload", files=PDF)
    assert r.status_code == 409


def test_correction_and_resubmission(admin):
    c = _register("service_provider", "organization", "fix@example.com")
    user_id = c.get("/auth/me").json()["id"]
    req_id = _checklist(c, "service_provider")["Provider company licence"]["requirement_id"]
    c.post(f"/service-provider/documents/{req_id}/upload", files=PDF)
    c.post("/service-provider/submit-for-review", json={"company_name": "Acme Co"})

    # A correction must say what to fix.
    assert _decide(admin, "service_provider", user_id, req_id, "rejected").status_code == 400
    r = _decide(admin, "service_provider", user_id, req_id, "rejected", note="The licence has expired; upload the renewed one.")
    assert r.status_code == 200
    profile = c.get("/service-provider/profile").json()
    assert profile["verification_state"] == "correction_required"
    doc = _checklist(c, "service_provider")["Provider company licence"]
    assert doc["status"] == "rejected" and "renewed" in doc["admin_note"]
    notes = c.get("/notifications").json()
    items = notes if isinstance(notes, list) else notes.get("items", [])
    assert any("renewed" in (n.get("body") or "") for n in items)

    # Can't resubmit until the flagged document is replaced.
    assert c.post("/service-provider/submit-for-review", json={"company_name": "Acme Co"}).status_code == 400
    assert c.post(f"/service-provider/documents/{req_id}/upload", files=PDF).status_code == 200
    r = c.post("/service-provider/submit-for-review", json={"company_name": "Acme Co"})
    assert r.status_code == 200 and r.json()["verification_state"] == "submitted"

    # Final rejection needs a reason, and is not resubmittable.
    assert admin.post(f"/admin/review/service-providers/{user_id}/reject", json={}).status_code == 400
    r = admin.post(f"/admin/review/service-providers/{user_id}/reject", json={"note": "Not a construction business."})
    assert r.status_code == 200 and r.json()["verification_state"] == "rejected"
    assert c.post(f"/service-provider/documents/{req_id}/upload", files=PDF).status_code == 409
    assert c.get("/account/identity").json()["stakeholder"]["status"]["eligible"] is False


def test_expiry_required_where_policy_says_so(admin):
    req = admin.post("/admin/requirements", json={"name": "Insurance", "applies_to": "owner", "requires_expiry": True}).json()
    c = _register("owner", "individual", "expiry@example.com")
    user_id = c.get("/auth/me").json()["id"]
    c.post(f"/owner/documents/{req['id']}/upload", files=PDF)
    assert _decide(admin, "owner", user_id, req["id"], "approved").status_code == 400
    soon = (datetime.utcnow() + timedelta(days=200)).date().isoformat()
    r = _decide(admin, "owner", user_id, req["id"], "approved", expires_on=soon)
    assert r.status_code == 200 and r.json()["expires_on"] == soon


def test_users_cannot_verify_themselves_or_bypass_gates(admin, db):
    owner = _register("owner", "individual", "self@example.com")
    owner_id = owner.get("/auth/me").json()["id"]
    sp = _register("service_provider", "individual", "selfsp@example.com")

    # No user-reachable way to set a verification status.
    assert owner.post(f"/admin/review/owners/{owner_id}/approve").status_code == 403
    assert owner.post(f"/admin/owners/{owner_id}/verification-status", json={"status": "approved"}).status_code == 403
    assert owner.get(f"/admin/owners/{owner_id}").status_code == 403

    # Backend gates hold regardless of what the frontend shows.
    assert owner.post("/projects", data={"title": "X", "address": "Y", "bid_deadline": "2030-01-01T00:00:00", "status": "open"}).status_code == 403
    assert sp.get("/service-provider/feed").status_code == 403


def test_document_access_stays_private(admin, db):
    c = _register("service_provider", "organization", "private@example.com")
    user_id = c.get("/auth/me").json()["id"]
    req_id = _checklist(c, "service_provider")["Provider company licence"]["requirement_id"]
    c.post(f"/service-provider/documents/{req_id}/upload", files=PDF)

    # The account holder's own listing never exposes a file link.
    assert "url" not in _checklist(c, "service_provider")["Provider company licence"]

    url = _admin_docs(admin, "service_provider", user_id)["Provider company licence"]["url"]
    path = url.split("://", 1)[-1].split("/", 1)[-1]
    anon = TestClient(app)
    assert anon.get("/" + path).status_code == 200  # signed, time-limited link works
    assert anon.get("/" + path.replace("sig=", "sig=x")).status_code == 403  # tampered link doesn't
    assert anon.get("/" + path.split("?")[0]).status_code == 422  # unsigned link doesn't

    # Another member of the same organization gets no access to its documents.
    org_id = c.get("/account/identity").json()["stakeholder"]["organization"]["id"]
    colleague = User(email="colleague@example.com", password_hash=hash_password("password123"), role=UserRole.service_provider, full_name="C")
    db.add(colleague)
    db.flush()
    db.add(OrganizationMembership(organization_id=org_id, user_id=colleague.id, role=MembershipRole.member))
    db.commit()
    cc = TestClient(app)
    cc.post("/auth/login", json={"email": "colleague@example.com", "password": "password123"})
    assert cc.get("/service-provider/documents").status_code == 404
    assert cc.get(f"/admin/service-providers/{user_id}").status_code == 403

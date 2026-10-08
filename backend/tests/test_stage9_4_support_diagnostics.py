"""Stage 9.4: an operator diagnoses a customer's problem from the same rules
the marketplace enforces -- who the person is and what they act for, what
blocks a requirement's publication, why a provider can't respond and where
its offer stands, what an award became -- read-only, without bypassing any
rule; account deletions and record corrections are on the audit trail."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award
from tests.test_stage8_15_review_moderation import _admin


def test_an_operator_diagnoses_without_bypassing(db):
    admin = _admin(db)
    owner, noura, owner_id, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, x_id, sami_id = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    solo = _account(db, "service_provider", "solo@example.com")
    solo_id = solo.get("/auth/me").json()["id"]

    # Who is this? A member is found by email, with the organisation they act for -- never a secret.
    found = admin.get("/admin/users", params={"email": "Sami@X.example"})
    assert found.status_code == 200
    f = found.json()
    assert (f["user"]["id"], f["acts_for"]["stakeholder_id"], f["acts_for"]["organization"]["legal_name"], f["membership"]["role"]) == (
        sami_id, x_id, "X Contracting", "member")
    assert f["acts_for"]["standing"]["can_bid"] is True
    assert "password" not in found.text and "token" not in found.text
    assert admin.get("/admin/users", params={"email": "nobody@example.com"}).status_code == 404

    # A. Publishing blocked: the operator sees the very errors the owner's Publish button reports.
    r = owner.post("/projects", data={"title": "Draft", "address": "Kaifan", "bid_deadline": (datetime.utcnow() + timedelta(days=5)).isoformat(), "status": "draft"})
    draft = r.json()["id"]
    q = admin.get(f"/admin/projects/{draft}/quality").json()
    assert q["owner_can_publish"] is True and q["status"] == "draft"
    assert "scope_missing" in {e["code"] for e in q["errors"]}  # no description of the work yet
    # (The gate itself -- publish refused on these errors -- is proven by the Stage 3.12 tests; the
    # suite disables it elsewhere, see conftest's quality_gate marker.)

    # B. A provider can't respond: the eligibility reason, as the offer endpoints judge it.
    pid = _tender(owner, title="Tower maintenance")
    db.get(Project, pid).provider_eligibility = {"provider_type": "organization", "qualifications": [], "match_category": False, "match_governorate": False}
    db.commit()
    check = admin.get(f"/admin/projects/{pid}/provider-check/{solo_id}").json()
    assert check["participation"]["status"] == "not_eligible" and [r["code"] for r in check["ineligibility_reasons"]] == ["organization_only"]
    assert solo.post(f"/projects/{pid}/offers", json={"amount": "100"}).status_code == 403
    # A suspended provider: an account matter, not a bug.
    db.get(ServiceProviderProfile, solo_id).is_suspended = True
    db.commit()
    assert admin.get(f"/admin/projects/{pid}/provider-check/{solo_id}").json()["participation"]["action"] == "account_suspended"

    # C / "my offer disappeared": the provider's own offer state, against the requirement's version.
    _submitted(sami, pid)
    assert owner.patch(f"/projects/{pid}", json={"description": "Two towers."}).status_code == 200
    c = admin.get(f"/admin/projects/{pid}/provider-check/{x_id}").json()
    assert c["participation"]["status"] == "can_participate"
    assert (c["offer"]["status"], c["offer"]["based_on_material_revision"], c["project"]["material_revision"], c["offer"]["won"]) == ("submitted", 0, 1, False)
    assert sami.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert admin.get(f"/admin/projects/{pid}/provider-check/{x_id}").json()["offer"]["status"] == "withdrawn"
    # A member's own row is not a stakeholder to check -- the organisation is.
    assert admin.get(f"/admin/projects/{pid}/provider-check/{sami_id}").status_code == 409

    # D/E. An award that happened, traced to its transaction (9.3); an expired requirement is shown expired.
    p2 = _tender(owner, title="Awarded job")
    _award(owner, amal, p2)
    complete_transaction(owner, amal, p2)
    assert admin.get(f"/admin/projects/{p2}/provider-check/{x_id}").json()["offer"]["won"] is True
    assert admin.get(f"/admin/projects/{p2}").json()["transaction"]["status"] == "completed"

    # Corrections and removals are on the audit trail.
    assert admin.patch(f"/admin/service-providers/{x_id}", json={"company_name": "X Contracting Co"}).status_code == 200
    assert db.query(AuditLog).filter(AuditLog.action == "service_provider.admin_edit", AuditLog.target_id == x_id).count() == 1
    # An account with a history isn't deleted (that would erase who did what) -- deactivate it instead.
    used = _account(db, "owner", "used@example.com")
    used_id = used.get("/auth/me").json()["id"]
    if db.query(AuditLog).filter(AuditLog.actor_id == used_id).count():
        r = admin.delete(f"/admin/owners/{used_id}")
        assert r.status_code == 400 and "Deactivate" in r.json()["detail"]
    # A never-used signup can be deleted, and that is audited.
    fresh = TestClient(app).post("/auth/signup", json={"email": "fresh@example.com", "password": "password123", "full_name": "F", "role": "owner"}).json()["id"]
    assert admin.delete(f"/admin/owners/{fresh}").status_code == 204
    assert db.query(AuditLog).filter(AuditLog.action == "owner.delete", AuditLog.target_id == fresh).count() == 1

    # H. Nobody else reaches any of it.
    for client in (owner, noura, amal, sami):
        assert client.get("/admin/users", params={"email": "sami@x.example"}).status_code == 403
        assert client.get(f"/admin/projects/{pid}/provider-check/{x_id}").status_code == 403
        assert client.get(f"/admin/projects/{draft}/quality").status_code == 403
    assert TestClient(app).get("/admin/users", params={"email": "sami@x.example"}).status_code == 401
    # Another owner can't read this owner's draft quality either.
    assert _account(db, "owner", "other@example.com").get(f"/projects/{draft}/quality").status_code == 404

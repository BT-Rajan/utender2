"""Step 3: a registered account establishes who it represents.

Each scenario answers the acceptance questions from GET /account/identity:
who is logged in, individual or organization, which organization, the
person's authority in it, whether it is verified, which side, and which
identity marketplace actions are recorded under."""
import pytest
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.enums import MembershipRole, UserRole, VerificationStatus
from app.models.organization import Organization, OrganizationMembership
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User


def _signup(role: str, email: str, full_name: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": full_name, "role": role})
    assert r.status_code == 201, r.text
    return c


@pytest.mark.parametrize("role", ["owner", "service_provider"])
def test_individual_stakeholder(db, role):
    c = _signup(role, f"ind-{role}@example.com", "Sara Ahmad")

    ident = c.get("/account/identity").json()
    assert ident["person"]["full_name"] == "Sara Ahmad"
    assert ident["role"] == role
    assert ident["stakeholder"]["status"] == {
        "account_created": True,
        "stakeholder_established": False,
        "verified": False,
        "eligible": False,
        "verification_status": "incomplete",
        "marketplace_status": "documents_incomplete",
    }
    assert ident["acting_as"] is None  # nothing can act until established

    r = c.put("/account/stakeholder", json={"type": "individual"})
    assert r.status_code == 200, r.text
    ident = r.json()
    assert ident["stakeholder"]["type"] == "individual"
    assert ident["stakeholder"]["organization"] is None
    assert ident["stakeholder"]["status"]["stakeholder_established"] is True
    assert ident["acting_as"] == {
        "kind": "individual",
        "stakeholder_id": ident["person"]["user_id"],
        "name": "Sara Ahmad",
        "user_id": ident["person"]["user_id"],
        "organization_id": None,
    }
    assert db.query(Organization).count() == 0


@pytest.mark.parametrize("role", ["owner", "service_provider"])
def test_organization_stakeholder(db, role):
    c = _signup(role, f"org-{role}@example.com", "Khalid Nasser")

    # An organization needs a legal name and the person's confirmation of authority.
    assert c.put("/account/stakeholder", json={"type": "organization", "legal_name": "Gulf Holdings W.L.L."}).status_code == 400
    assert c.put("/account/stakeholder", json={"type": "organization", "legal_name": " ", "authorized": True}).status_code == 400

    r = c.put(
        "/account/stakeholder",
        json={"type": "organization", "legal_name": "Gulf Holdings W.L.L.", "position": "General Manager", "authorized": True},
    )
    assert r.status_code == 200, r.text
    ident = r.json()
    person_id = ident["person"]["user_id"]
    org = ident["stakeholder"]["organization"]
    assert ident["stakeholder"]["type"] == "organization"
    assert ident["stakeholder"]["display_name"] == "Gulf Holdings W.L.L."
    assert org["legal_name"] == "Gulf Holdings W.L.L."
    assert org["membership"] == {"role": "admin", "position": "General Manager"}
    assert org["authorized_representative"]["user_id"] == person_id
    assert ident["acting_as"]["kind"] == "organization"
    assert ident["acting_as"]["organization_id"] == org["id"]
    assert ident["acting_as"]["stakeholder_id"] == person_id  # the profile marketplace records point at

    # The login is a person, the organization a separate record.
    assert db.get(User, person_id).full_name == "Khalid Nasser"
    assert db.get(Organization, org["id"]).legal_name == "Gulf Holdings W.L.L."
    if role == "service_provider":
        assert db.get(ServiceProviderProfile, person_id).company_name == "Gulf Holdings W.L.L."

    # Correcting the name updates the same organization, not a new one.
    c.put("/account/stakeholder", json={"type": "organization", "legal_name": "Gulf Holdings Co.", "authorized": True})
    assert db.query(Organization).count() == 1

    # Switching to individual removes the now-unused organization.
    c.put("/account/stakeholder", json={"type": "individual"})
    assert db.query(Organization).count() == 0 and db.query(OrganizationMembership).count() == 0


def test_organization_verified_and_eligible_follow_the_profile(db):
    c = _signup("owner", "verified-org@example.com", "Mona")
    person_id = c.get("/auth/me").json()["id"]
    c.put("/account/stakeholder", json={"type": "organization", "legal_name": "Mona Estates", "authorized": True})

    profile = db.get(OwnerProfile, person_id)
    profile.verification_status = VerificationStatus.approved
    db.commit()
    status = c.get("/account/identity").json()["stakeholder"]["status"]
    assert status["verified"] is True and status["eligible"] is True

    # Once verified the identity is locked: an approved organization can't
    # quietly become something else.
    r = c.put("/account/stakeholder", json={"type": "individual"})
    assert r.status_code == 409
    assert c.get("/account/identity").json()["stakeholder"]["editable"] is False


def test_verification_requires_an_established_stakeholder(db):
    c = _signup("service_provider", "gate@example.com", "Ali")
    r = c.post("/service-provider/submit-for-review", json={"company_name": "Ali Works"})
    assert r.status_code == 400 and "represents" in r.json()["detail"]
    c.put("/account/stakeholder", json={"type": "individual"})
    assert c.post("/service-provider/submit-for-review", json={"company_name": "Ali Works"}).status_code == 200
    # Under review: identity can no longer change.
    assert c.put("/account/stakeholder", json={"type": "individual"}).status_code == 409


def test_one_organization_can_hold_several_people(db):
    rep = _signup("service_provider", "rep@example.com", "Rep")
    org_id = rep.put(
        "/account/stakeholder", json={"type": "organization", "legal_name": "Build Co", "position": "Owner", "authorized": True}
    ).json()["stakeholder"]["organization"]["id"]

    colleague = User(email="colleague@example.com", password_hash=hash_password("password123"), role=UserRole.service_provider, full_name="Colleague")
    db.add(colleague)
    db.flush()
    db.add(OrganizationMembership(organization_id=org_id, user_id=colleague.id, role=MembershipRole.member))
    db.commit()

    org = rep.get("/account/identity").json()["stakeholder"]["organization"]
    assert org["member_count"] == 2
    assert org["authorized_representative"]["email"] == "rep@example.com"

    # The representative can't switch away and orphan a colleague's organization.
    rep.put("/account/stakeholder", json={"type": "individual"})
    assert db.get(Organization, org_id) is not None


def test_admin_sees_who_the_account_represents(db):
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    admin = TestClient(app)
    admin.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})

    sp = _signup("service_provider", "sp-admin@example.com", "Nora")
    sp_id = sp.get("/auth/me").json()["id"]
    sp.put("/account/stakeholder", json={"type": "organization", "legal_name": "Nora Contracting", "position": "Director", "authorized": True})
    owner = _signup("owner", "owner-admin@example.com", "Omar")
    owner_id = owner.get("/auth/me").json()["id"]
    owner.put("/account/stakeholder", json={"type": "individual"})

    sp_view = admin.get(f"/admin/service-providers/{sp_id}").json()["stakeholder"]
    assert sp_view["type"] == "organization"
    assert sp_view["organization"]["authorized_representative"] == {
        "user_id": sp_id, "full_name": "Nora", "email": "sp-admin@example.com", "position": "Director"
    }
    assert admin.get(f"/admin/owners/{owner_id}").json()["stakeholder"]["type"] == "individual"

    # Admin accounts never represent a stakeholder.
    ident = admin.get("/account/identity").json()
    assert ident["stakeholder"] is None and ident["acting_as"] is None
    assert admin.put("/account/stakeholder", json={"type": "individual"}).status_code == 403

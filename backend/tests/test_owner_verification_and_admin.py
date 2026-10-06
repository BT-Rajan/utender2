"""Owner verification (civil ID / land ownership documents -> admin
approval gate), admin owner management (list, approve, reject, suspend,
delete), and the admin all-offers view -- added in response to a user
request after the original 24-pass effort, following the same
document-review pattern PASS 5/6 built for service providers.
"""
from datetime import datetime, timedelta

import app.db as db_module
from fastapi.testclient import TestClient
from app.main import app


# In production these two rows come from Alembic migration 0005's data
# seed (see alembic/versions/0005_owner_verification.py) -- this test
# suite uses Base.metadata.create_all() (schema only, per conftest.py's
# isolated_backend fixture), which never runs data migrations, so tests
# that exercise the owner document flow need to seed them the same way
# the migration does before any owner signs up (ensure_owner_document_rows
# only stubs rows for requirements that already exist at signup time).
def _seed_owner_requirements(db):
    from app.models.document import DocumentRequirement
    from app.models.enums import UserRole

    for name, description in [
        ("Civil ID", "A government-issued civil ID / national ID for the property owner."),
        ("Land Ownership Proof", "A deed, title, or other document proving ownership of the property being listed."),
    ]:
        db.add(DocumentRequirement(name=name, description=description, is_required=True, applies_to=UserRole.owner))
    db.commit()


def test_owner_signup_gets_seeded_document_checklist():
    db = db_module.SessionLocal()
    _seed_owner_requirements(db)

    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner One", "role": "owner"},
    )
    assert r.status_code == 201

    r = client.get("/owner/profile")
    assert r.status_code == 200
    assert r.json()["verification_status"] == "incomplete"
    assert r.json()["marketplace_status"] == "documents_incomplete"

    r = client.get("/owner/requirements")
    assert r.status_code == 200
    names = {req["name"] for req in r.json()}
    assert names == {"Civil ID", "Land Ownership Proof"}

    r = client.get("/owner/documents")
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert all(d["status"] == "not_submitted" for d in r.json())


def test_owner_requirements_and_service_provider_requirements_are_scoped_separately():
    from app.models.document import DocumentRequirement
    from app.models.enums import UserRole

    db = db_module.SessionLocal()
    _seed_owner_requirements(db)
    db.add(DocumentRequirement(name="Trade License", is_required=True, applies_to=UserRole.service_provider))
    db.commit()

    owner_client = TestClient(app)
    owner_client.post(
        "/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"}
    )
    service_provider_client = TestClient(app)
    service_provider_client.post(
        "/auth/signup",
        json={"email": "c1@example.com", "password": "password123", "full_name": "C", "role": "service_provider", "company_name": "Acme"},
    )

    owner_reqs = {r["name"] for r in owner_client.get("/owner/requirements").json()}
    service_provider_reqs = {r["name"] for r in service_provider_client.get("/service-provider/requirements").json()}
    assert owner_reqs == {"Civil ID", "Land Ownership Proof"}
    assert service_provider_reqs == {"Trade License"}
    assert owner_reqs.isdisjoint(service_provider_reqs)


def _signup_admin(db):
    from app.auth.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User

    admin = User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin")
    db.add(admin)
    db.commit()
    admin_client = TestClient(app)
    admin_client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    return admin_client


def test_owner_blocked_from_posting_until_approved_then_unblocked():
    db = db_module.SessionLocal()
    _seed_owner_requirements(db)
    admin_client = _signup_admin(db)

    owner_client = TestClient(app)
    r = owner_client.post(
        "/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"}
    )
    owner_id = r.json()["id"]

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()

    # Not yet verified -> blocked from posting.
    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": future, "status": "open"})
    assert r.status_code == 403
    assert r.json()["detail"] == "not_approved"

    # Upload both required documents.
    reqs = owner_client.get("/owner/requirements").json()
    for req in reqs:
        r = owner_client.post(
            f"/owner/documents/{req['id']}/upload",
            files={"file": ("doc.pdf", b"fake pdf bytes", "application/pdf")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pending"

    # Submit for review.
    r = owner_client.post("/owner/submit-for-review")
    assert r.status_code == 200
    assert r.json()["verification_status"] == "pending_review"

    # Still blocked -- pending review isn't approved yet.
    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": future, "status": "open"})
    assert r.status_code == 403

    # Admin sees the owner and their pending documents.
    r = admin_client.get("/admin/owners")
    assert r.status_code == 200
    listed = next(o for o in r.json() if o["user_id"] == owner_id)
    assert listed["verification_status"] == "pending_review"
    assert listed["email"] == "owner1@example.com"

    r = admin_client.get(f"/admin/owners/{owner_id}")
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert len(docs) == 2
    assert all(d["status"] == "pending" for d in docs)

    # Approving the OWNER before all documents are individually approved
    # is rejected, same guard as the service provider flow.
    r = admin_client.post(f"/admin/review/owners/{owner_id}/approve")
    assert r.status_code == 400

    # Admin approves each document.
    for d in docs:
        r = admin_client.post(
            "/admin/review/owner-documents",
            json={"owner_id": owner_id, "requirement_id": d["requirement_id"], "decision": "approved"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    # Now the overall approval succeeds.
    r = admin_client.post(f"/admin/review/owners/{owner_id}/approve")
    assert r.status_code == 200
    assert r.json()["verification_status"] == "approved"
    assert r.json()["marketplace_status"] == "verified_active"

    # Owner notified of activation.
    r = owner_client.get("/notifications")
    assert any(n["type"] == "owner_verification_activated" for n in r.json())

    # Owner can now post a project.
    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": future, "status": "open"})
    assert r.status_code == 201


def test_admin_document_rejection_reopens_owner_for_changes():
    db = db_module.SessionLocal()
    _seed_owner_requirements(db)
    admin_client = _signup_admin(db)

    owner_client = TestClient(app)
    owner_client.post(
        "/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"}
    )
    reqs = owner_client.get("/owner/requirements").json()
    for req in reqs:
        owner_client.post(f"/owner/documents/{req['id']}/upload", files={"file": ("doc.pdf", b"x", "application/pdf")})
    owner_client.post("/owner/submit-for-review")

    from app.models.owner import OwnerProfile
    owner_row = db.query(OwnerProfile).first()
    owner_id = owner_row.user_id

    r = admin_client.post(
        "/admin/review/owner-documents",
        json={"owner_id": owner_id, "requirement_id": reqs[0]["id"], "decision": "rejected", "note": "Blurry photo"},
    )
    assert r.status_code == 200
    assert r.json()["admin_note"] == "Blurry photo"

    r = owner_client.get("/owner/profile")
    assert r.json()["verification_status"] == "changes_requested"

    r = owner_client.get("/notifications")
    assert any(n["type"] == "owner_document_rejected" for n in r.json())


def test_admin_suspend_reactivate_and_delete_guard_for_owners():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)

    # Owner with a posted project -> deletion must be refused, suspend allowed.
    owner_client = TestClient(app)
    r = owner_client.post(
        "/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"}
    )
    owner_id = r.json()["id"]

    from app.models.owner import OwnerProfile
    from app.models.enums import VerificationStatus
    op = db.get(OwnerProfile, owner_id)
    op.verification_status = VerificationStatus.approved
    db.commit()

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()
    owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": future, "status": "open"})

    r = admin_client.delete(f"/admin/owners/{owner_id}")
    assert r.status_code == 400
    assert "Suspend" in r.json()["detail"]

    r = admin_client.post(f"/admin/owners/{owner_id}/suspend", json={"suspended": True})
    assert r.status_code == 200
    assert r.json()["is_suspended"] is True
    assert r.json()["marketplace_status"] == "suspended"

    # A suspended owner is blocked from posting even though verification_status is still "approved".
    r = owner_client.post("/projects", data={"title": "Fence", "address": "2 Oak Ave", "bid_deadline": future, "status": "open"})
    assert r.status_code == 403

    r = admin_client.post(f"/admin/owners/{owner_id}/suspend", json={"suspended": False})
    assert r.status_code == 200
    assert r.json()["is_suspended"] is False

    r = owner_client.get("/notifications")
    types = {n["type"] for n in r.json()}
    assert "owner_suspended" in types
    assert "owner_reactivated" in types

    # A second, fresh owner with NO projects can be deleted outright.
    owner2_client = TestClient(app)
    r = owner2_client.post(
        "/auth/signup", json={"email": "owner2@example.com", "password": "password123", "full_name": "Owner Two", "role": "owner"}
    )
    owner2_id = r.json()["id"]
    r = admin_client.delete(f"/admin/owners/{owner2_id}")
    assert r.status_code == 204

    r = admin_client.get("/admin/owners")
    assert all(o["user_id"] != owner2_id for o in r.json())


def test_non_admin_cannot_reach_owner_admin_endpoints():
    owner_client = TestClient(app)
    r = owner_client.post(
        "/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"}
    )
    owner_id = r.json()["id"]

    r = owner_client.get("/admin/owners")
    assert r.status_code == 403
    r = owner_client.post(f"/admin/owners/{owner_id}/suspend", json={"suspended": True})
    assert r.status_code == 403
    r = owner_client.delete(f"/admin/owners/{owner_id}")
    assert r.status_code == 403


def test_admin_created_by_promoting_an_owner_does_not_appear_in_owners_list():
    """Regression test: the README documents the ONLY way to create an
    admin as "sign up as owner (or service provider), then flip that row's role
    column directly in the database." That leaves a real owner_profiles
    row behind for an account that is no longer an owner. A live UI smoke
    test caught this: /admin/owners listed the admin itself (with a
    stray "incomplete" verification status), and clicking into it instead
    of the real owner under test led to editing the wrong account.
    """
    db = db_module.SessionLocal()

    # Sign up as an owner, then promote to admin exactly the way the
    # README instructs -- NOT via _signup_admin's direct User(role=admin)
    # insert, which never creates an OwnerProfile at all and so wouldn't
    # reproduce this bug.
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={"email": "promoted-admin@example.com", "password": "password123", "full_name": "Promoted Admin", "role": "owner"},
    )
    promoted_id = r.json()["id"]

    from app.models.user import User
    from app.models.enums import UserRole

    db.query(User).filter(User.id == promoted_id).update({"role": UserRole.admin})
    db.commit()

    admin_client = TestClient(app)
    admin_client.post("/auth/login", json={"email": "promoted-admin@example.com", "password": "password123"})

    r = admin_client.get("/admin/owners")
    assert r.status_code == 200
    assert all(o["user_id"] != promoted_id for o in r.json())

    r = admin_client.get(f"/admin/owners/{promoted_id}")
    assert r.status_code == 404

    r = admin_client.post(f"/admin/review/owners/{promoted_id}/approve")
    assert r.status_code == 404

    r = admin_client.post(f"/admin/owners/{promoted_id}/suspend", json={"suspended": True})
    assert r.status_code == 404

    r = admin_client.delete(f"/admin/owners/{promoted_id}")
    assert r.status_code == 404


def test_admin_created_by_promoting_a_service_provider_does_not_appear_in_service_providers_list():
    """Same bug, same fix, one level over: this class of bug (a promoted
    admin's leftover profile row showing up in an admin management list)
    predates this session's owner work entirely -- it was already true
    for service providers (PASS 6) and only surfaced now because fixing it for
    owners meant re-reading every admin list/detail/mutation endpoint
    side by side. Fixed symmetrically in the same commit rather than left
    sitting next to the owner fix as a known twin.
    """
    db = db_module.SessionLocal()

    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={
            "email": "promoted-admin-2@example.com",
            "password": "password123",
            "full_name": "Promoted Admin Two",
            "role": "service_provider",
            "company_name": "Soon To Be Admin LLC",
        },
    )
    promoted_id = r.json()["id"]

    from app.models.user import User
    from app.models.enums import UserRole

    db.query(User).filter(User.id == promoted_id).update({"role": UserRole.admin})
    db.commit()

    admin_client = TestClient(app)
    admin_client.post("/auth/login", json={"email": "promoted-admin-2@example.com", "password": "password123"})

    r = admin_client.get("/admin/service-providers")
    assert r.status_code == 200
    assert all(c["user_id"] != promoted_id for c in r.json())

    r = admin_client.get(f"/admin/service-providers/{promoted_id}")
    assert r.status_code == 404

    r = admin_client.post(f"/admin/service-providers/{promoted_id}/suspend", json={"suspended": True})
    assert r.status_code == 404

    r = admin_client.post(f"/admin/service-providers/{promoted_id}/payment-override", json={"reason": "test"})
    assert r.status_code == 404

    r = admin_client.delete(f"/admin/service-providers/{promoted_id}")
    assert r.status_code == 404


def test_admin_sees_all_offers_across_every_project_unredacted():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)

    from app.models.document import ServiceProviderDocument
    from app.models.enums import DocumentStatus

    def make_active_service_provider(email, company):
        client = TestClient(app)
        r = client.post(
            "/auth/signup",
            json={"email": email, "password": "password123", "full_name": "C", "role": "service_provider", "company_name": company},
        )
        cid = r.json()["id"]
        for doc in db.query(ServiceProviderDocument).filter_by(service_provider_id=cid).all():
            doc.status = DocumentStatus.approved
        db.commit()
        admin_client.post(f"/admin/review/service-providers/{cid}/approve")
        admin_client.post(f"/admin/service-providers/{cid}/payment-override", json={"reason": "test"})
        return client, cid

    owner_client = TestClient(app)
    r = owner_client.post(
        "/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"}
    )
    owner_id = r.json()["id"]
    from app.models.owner import OwnerProfile
    from app.models.enums import VerificationStatus
    db.get(OwnerProfile, owner_id).verification_status = VerificationStatus.approved
    db.commit()

    c1, c1_id = make_active_service_provider("c1@example.com", "Acme")
    c2, c2_id = make_active_service_provider("c2@example.com", "BuildCo")

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()
    r = owner_client.post(
        "/projects",
        data={"title": "Sealed job", "address": "1 Main St", "bid_deadline": future, "status": "open", "tender_type": "sealed"},
    )
    project_id = r.json()["id"]
    c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00"})
    c2.post(f"/projects/{project_id}/offers", json={"amount": "4800.00"})

    # Sealed and still open: the OWNER-facing endpoint redacts these.
    r = owner_client.get(f"/owner/projects/{project_id}/offers")
    assert all(o["service_provider_id"] is None for o in r.json())

    # The ADMIN-facing all-offers endpoint does not redact -- admin is the
    # platform operator, not the party the sealed-bid rule protects
    # against, and can already see the award record regardless of seal
    # status.
    r = admin_client.get("/admin/offers")
    assert r.status_code == 200
    all_offers = r.json()
    assert len(all_offers) == 2
    companies = {o["service_provider_company_name"] for o in all_offers}
    assert companies == {"Acme", "BuildCo"}
    amounts = {o["amount"] for o in all_offers}
    assert amounts == {"5000.00", "4800.00"}
    assert all(o["project_title"] == "Sealed job" for o in all_offers)

    r = owner_client.get("/admin/offers")
    assert r.status_code == 403

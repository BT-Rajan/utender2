"""Admin moderation over every owner's projects and every service provider's
offers on them: list/detail (including a per-owner drill-down), edit,
suspend/reactivate, and delete -- added after the owner-verification pass
in response to a follow-up user request ("i also want to see the posted
offers by each owner and as an admin i shall be able to edit, suspend,
delete any posted offers by any owner").
"""
from datetime import datetime, timedelta

import app.db as db_module
from fastapi.testclient import TestClient
from app.main import app


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


def _make_approved_owner(db, email="owner1@example.com"):
    from app.models.owner import OwnerProfile
    from app.models.enums import VerificationStatus

    client = TestClient(app)
    r = client.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "Owner", "role": "owner"})
    owner_id = r.json()["id"]
    db.get(OwnerProfile, owner_id).verification_status = VerificationStatus.approved
    db.commit()
    return client, owner_id


def _make_active_service_provider(db, admin_client, email, company):
    from app.models.document import ServiceProviderDocument
    from app.models.enums import DocumentStatus

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


def _future() -> str:
    return (datetime.utcnow() + timedelta(days=7)).isoformat()


def test_admin_lists_all_projects_and_drills_into_owner_projects():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)
    owner_client, owner_id = _make_approved_owner(db)

    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": _future(), "status": "open"})
    project_id = r.json()["id"]

    r = admin_client.get("/admin/projects")
    assert r.status_code == 200
    listed = next(p for p in r.json() if p["id"] == project_id)
    assert listed["owner_email"] == "owner1@example.com"
    assert listed["offer_count"] == 0
    assert listed["is_suspended"] is False

    r = admin_client.get(f"/admin/owners/{owner_id}/projects")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == project_id

    r = owner_client.get("/admin/projects")
    assert r.status_code == 403


def test_admin_project_detail_shows_offers_unredacted_even_when_sealed():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)
    owner_client, owner_id = _make_approved_owner(db)
    c1, c1_id = _make_active_service_provider(db, admin_client, "c1@example.com", "Acme")

    r = owner_client.post(
        "/projects",
        data={"title": "Sealed job", "address": "1 Main St", "bid_deadline": _future(), "status": "open", "tender_type": "sealed"},
    )
    project_id = r.json()["id"]
    c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00"})

    r = admin_client.get(f"/admin/projects/{project_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["project"]["title"] == "Sealed job"
    assert len(body["offers"]) == 1
    assert body["offers"][0]["service_provider_id"] == c1_id
    assert body["offers"][0]["amount"] == "5000.000"
    assert body["offers"][0]["service_provider_company_name"] == "Acme"


def test_admin_edit_project_fields():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)
    owner_client, owner_id = _make_approved_owner(db)

    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": _future(), "status": "open"})
    project_id = r.json()["id"]

    r = admin_client.patch(f"/admin/projects/{project_id}", json={"title": "Deck (corrected)", "trade": "Carpentry"})
    assert r.status_code == 200
    assert r.json()["title"] == "Deck (corrected)"
    assert r.json()["trade"] == "Carpentry"

    r = owner_client.get(f"/projects/{project_id}")
    assert r.json()["title"] == "Deck (corrected)"

    r = admin_client.patch(f"/admin/projects/{project_id}", json={"title": "   "})
    assert r.status_code == 400

    r = admin_client.patch(f"/admin/projects/{project_id}", json={})
    assert r.status_code == 400


def test_admin_suspend_project_hides_from_feed_and_blocks_bidding():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)
    owner_client, owner_id = _make_approved_owner(db)
    c1, c1_id = _make_active_service_provider(db, admin_client, "c1@example.com", "Acme")

    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": _future(), "status": "open"})
    project_id = r.json()["id"]

    r = c1.get("/service-provider/feed")
    assert any(p["id"] == project_id for p in r.json())

    r = admin_client.post(f"/admin/projects/{project_id}/suspend", json={"suspended": True})
    assert r.status_code == 200
    assert r.json()["is_suspended"] is True

    r = c1.get("/service-provider/feed")
    assert all(p["id"] != project_id for p in r.json())

    r = c1.get(f"/projects/{project_id}")
    assert r.status_code == 404

    r = c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00"})
    assert r.status_code == 400
    assert "suspended" in r.json()["detail"].lower()

    # The owner is notified, and can still see their own project.
    r = owner_client.get("/notifications")
    assert any(n["type"] == "project_suspended" for n in r.json())
    r = owner_client.get(f"/projects/{project_id}")
    assert r.status_code == 200

    r = admin_client.post(f"/admin/projects/{project_id}/suspend", json={"suspended": False})
    assert r.status_code == 200
    r = c1.get("/service-provider/feed")
    assert any(p["id"] == project_id for p in r.json())
    r = owner_client.get("/notifications")
    assert any(n["type"] == "project_reactivated" for n in r.json())


def test_admin_delete_project_guard_and_success():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)
    owner_client, owner_id = _make_approved_owner(db)
    c1, c1_id = _make_active_service_provider(db, admin_client, "c1@example.com", "Acme")

    r = owner_client.post("/projects", data={"title": "Has offer", "address": "1 Main St", "bid_deadline": _future(), "status": "open"})
    project_with_offer = r.json()["id"]
    c1.post(f"/projects/{project_with_offer}/offers", json={"amount": "5000.00"})

    r = admin_client.delete(f"/admin/projects/{project_with_offer}")
    assert r.status_code == 400
    assert "Suspend" in r.json()["detail"]

    r = owner_client.post("/projects", data={"title": "No offers", "address": "2 Oak Ave", "bid_deadline": _future(), "status": "open"})
    empty_project_id = r.json()["id"]

    r = admin_client.delete(f"/admin/projects/{empty_project_id}")
    assert r.status_code == 204

    r = admin_client.get(f"/admin/projects/{empty_project_id}")
    assert r.status_code == 404


def test_admin_edit_offer_snapshots_revision():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)
    owner_client, owner_id = _make_approved_owner(db)
    c1, c1_id = _make_active_service_provider(db, admin_client, "c1@example.com", "Acme")

    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": _future(), "status": "open"})
    project_id = r.json()["id"]
    r = c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00", "message": "original"})
    offer_id = r.json()["id"]

    r = admin_client.patch(f"/admin/offers/{offer_id}", json={"amount": "4500.00", "message": "corrected typo"})
    assert r.status_code == 200
    assert r.json()["amount"] == "4500.000"
    assert r.json()["message"] == "corrected typo"
    assert r.json()["revision"] == 2

    r = c1.get(f"/projects/{project_id}/offers/mine/history")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["amount"] == "5000.000"
    assert r.json()[0]["message"] == "original"

    r = admin_client.patch(f"/admin/offers/{offer_id}", json={"amount": "0"})
    assert r.status_code == 400
    r = admin_client.patch(f"/admin/offers/{offer_id}", json={})
    assert r.status_code == 400


def test_admin_suspend_offer_hides_from_owner_evaluation_and_blocks_award():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)
    owner_client, owner_id = _make_approved_owner(db)
    c1, c1_id = _make_active_service_provider(db, admin_client, "c1@example.com", "Acme")
    c2, c2_id = _make_active_service_provider(db, admin_client, "c2@example.com", "BuildCo")

    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": _future(), "status": "open"})
    project_id = r.json()["id"]
    r = c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00"})
    offer1_id = r.json()["id"]
    c2.post(f"/projects/{project_id}/offers", json={"amount": "4800.00"})

    r = admin_client.post(f"/admin/offers/{offer1_id}/suspend", json={"suspended": True})
    assert r.status_code == 200
    assert r.json()["is_suspended"] is True

    r = owner_client.get(f"/owner/projects/{project_id}/offers")
    assert all(o["id"] != offer1_id for o in r.json())
    assert len(r.json()) == 1

    r = c1.get("/notifications")
    assert any(n["type"] == "offer_suspended" for n in r.json())

    owner_client.post(f"/owner/projects/{project_id}/close")
    r = owner_client.post(f"/owner/projects/{project_id}/offers/{offer1_id}/approve")
    assert r.status_code == 400
    assert "suspended" in r.json()["detail"].lower()

    r = admin_client.post(f"/admin/offers/{offer1_id}/suspend", json={"suspended": False})
    assert r.status_code == 200
    r = owner_client.get(f"/owner/projects/{project_id}/offers")
    assert len(r.json()) == 2
    r = c1.get("/notifications")
    assert any(n["type"] == "offer_reactivated" for n in r.json())

    # Now awardable again.
    r = owner_client.post(f"/owner/projects/{project_id}/offers/{offer1_id}/approve")
    assert r.status_code == 200


def test_admin_delete_offer_guard_and_success():
    db = db_module.SessionLocal()
    admin_client = _signup_admin(db)
    owner_client, owner_id = _make_approved_owner(db)
    c1, c1_id = _make_active_service_provider(db, admin_client, "c1@example.com", "Acme")
    c2, c2_id = _make_active_service_provider(db, admin_client, "c2@example.com", "BuildCo")

    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": _future(), "status": "open"})
    project_id = r.json()["id"]
    r = c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00"})
    winning_offer_id = r.json()["id"]
    r = c2.post(f"/projects/{project_id}/offers", json={"amount": "4800.00"})
    losing_offer_id = r.json()["id"]

    owner_client.post(f"/owner/projects/{project_id}/close")
    owner_client.post(f"/owner/projects/{project_id}/offers/{winning_offer_id}/approve")

    r = admin_client.delete(f"/admin/offers/{winning_offer_id}")
    assert r.status_code == 400
    assert "award" in r.json()["detail"].lower()

    r = admin_client.delete(f"/admin/offers/{losing_offer_id}")
    assert r.status_code == 204

    r = admin_client.get(f"/admin/projects/{project_id}")
    assert all(o["id"] != losing_offer_id for o in r.json()["offers"])


def test_non_admin_cannot_reach_project_offer_moderation_endpoints():
    db = db_module.SessionLocal()
    owner_client, owner_id = _make_approved_owner(db)
    r = owner_client.post("/projects", data={"title": "Deck", "address": "1 Main St", "bid_deadline": _future(), "status": "open"})
    project_id = r.json()["id"]

    assert owner_client.get("/admin/projects").status_code == 403
    assert owner_client.get(f"/admin/projects/{project_id}").status_code == 403
    assert owner_client.patch(f"/admin/projects/{project_id}", json={"title": "hacked"}).status_code == 403
    assert owner_client.post(f"/admin/projects/{project_id}/suspend", json={"suspended": True}).status_code == 403
    assert owner_client.delete(f"/admin/projects/{project_id}").status_code == 403

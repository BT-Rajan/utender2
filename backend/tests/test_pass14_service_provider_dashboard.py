from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass14_service_provider_dashboard():
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    from app.auth.security import hash_password
    from app.models.document import ServiceProviderDocument
    from app.models.enums import DocumentStatus, UserRole
    from app.models.user import User

    db = db_module.SessionLocal()

    admin = User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin")
    db.add(admin)
    db.commit()
    admin_client = TestClient(app)
    admin_client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})

    owner_client = TestClient(app)
    _owner_signup_r = owner_client.post("/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"})
    from app.models.owner import OwnerProfile as _OwnerProfile
    from app.models.enums import VerificationStatus as _OwnerVerificationStatus
    _owner_approve_db = db_module.SessionLocal()
    _owner_approve_db.get(_OwnerProfile, _owner_signup_r.json()['id']).verification_status = _OwnerVerificationStatus.approved
    _owner_approve_db.commit()

    service_provider_client = TestClient(app)
    r = service_provider_client.post(
        "/auth/signup",
        json={"email": "c1@example.com", "password": "password123", "full_name": "C", "role": "service_provider", "company_name": "Acme"},
    )
    cid = r.json()["id"]

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()

    # ---------- my-bids works even before verification (unverified service provider, no bids yet) ----------
    r = service_provider_client.get("/service-provider/my-bids")
    check("my-bids accessible before verification (empty list)", r.status_code == 200 and r.json() == [])

    # ---------- activate service provider and place bids ----------
    for doc in db.query(ServiceProviderDocument).filter_by(service_provider_id=cid).all():
        doc.status = DocumentStatus.approved
    db.commit()
    admin_client.post(f"/admin/review/service-providers/{cid}/approve")
    admin_client.post(f"/admin/service-providers/{cid}/payment-override", json={"reason": "test activation"})

    r = owner_client.post("/projects", data={"title": "Roof job", "address": "1 Main St", "bid_deadline": future, "status": "open"})
    project1_id = r.json()["id"]
    r = owner_client.post("/projects", data={"title": "Fence job", "address": "2 Oak Ave", "bid_deadline": future, "status": "open"})
    project2_id = r.json()["id"]
    r = owner_client.post("/projects", data={"title": "Deck job", "address": "3 Pine Rd", "bid_deadline": future, "status": "open"})
    project3_id = r.json()["id"]

    service_provider_client.post(f"/projects/{project1_id}/offers", json={"amount": "1000.00"})
    service_provider_client.post(f"/projects/{project2_id}/offers", json={"amount": "2000.00"})
    service_provider_client.post(f"/projects/{project3_id}/offers", json={"amount": "3000.00"})
    service_provider_client.post(f"/projects/{project3_id}/offers/withdraw")

    r = service_provider_client.get("/service-provider/my-bids")
    check("my-bids returns 3 bids total (including withdrawn)", r.status_code == 200 and len(r.json()) == 3)

    bids = {b["project_id"]: b for b in r.json()}
    check("bid amounts correct", float(bids[project1_id]["amount"]) == 1000.00 and float(bids[project2_id]["amount"]) == 2000.00)
    check("withdrawn bid status reflected", bids[project3_id]["offer_status"] == "withdrawn")
    check("live bid status reflected", bids[project1_id]["offer_status"] == "submitted")
    check("project title included", bids[project1_id]["project_title"] == "Roof job")
    check("project status included", bids[project1_id]["project_status"] == "open")

    # award one -> reflected as approved in my-bids
    owner_client.post(f"/owner/projects/{project1_id}/close")
    offer1_id = bids[project1_id]["offer_id"]
    owner_client.post(f"/owner/projects/{project1_id}/offers/{offer1_id}/approve")

    r = service_provider_client.get("/service-provider/my-bids")
    bids2 = {b["project_id"]: b for b in r.json()}
    check("awarded bid shows offer_status=approved", bids2[project1_id]["offer_status"] == "approved")
    check("awarded bid shows project_status=awarded", bids2[project1_id]["project_status"] == "awarded")

    # a different service provider with no bids sees an empty list, not another service provider's bids
    c2 = TestClient(app)
    c2.post("/auth/signup", json={"email": "c2@example.com", "password": "password123", "full_name": "C2", "role": "service_provider", "company_name": "BuildCo"})
    r = c2.get("/service-provider/my-bids")
    check("a service provider with no bids gets an empty list, not someone else's", r.status_code == 200 and r.json() == [])

    # owner cannot access the service-provider-only endpoint
    r = owner_client.get("/service-provider/my-bids")
    check("owner blocked from /service-provider/my-bids (403)", r.status_code == 403)

    # admin cannot access it either (role-scoped, not admin-scoped)
    r = admin_client.get("/service-provider/my-bids")
    check("admin blocked from /service-provider/my-bids (403)", r.status_code == 403)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

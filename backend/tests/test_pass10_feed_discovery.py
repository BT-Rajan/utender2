from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass10_feed_discovery():
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
    for doc in db.query(ServiceProviderDocument).filter_by(service_provider_id=cid).all():
        doc.status = DocumentStatus.approved
    db.commit()
    admin_client.post(f"/admin/review/service-providers/{cid}/approve")
    # Note: deliberately NOT granting payment override — feed browsing needs
    # only verification, per the existing soft-gate design.

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()

    owner_client.post("/projects", data={"title": "Roof replacement on Maple St", "address": "1 Maple St", "trade": "Roofing", "bid_deadline": future, "status": "open"})
    owner_client.post("/projects", data={"title": "Kitchen remodel", "address": "2 Oak Ave", "trade": "Carpentry", "bid_deadline": future, "status": "open"})
    owner_client.post("/projects", data={"title": "Fence repair", "address": "3 Pine Rd", "trade": "Fencing", "description": "Replace 40ft of cedar fence", "bid_deadline": future, "status": "open"})

    # created_at has second-level granularity (true of MySQL DATETIME too,
    # not just SQLite) — three inserts in the same test process can land in
    # the same second, making "newest first" order otherwise undefined.
    # Force distinct timestamps directly so the sort=newest test is meaningful.
    from app.models.project import Project as _Project

    _offsets_minutes_ago = {"Roof replacement on Maple St": 3, "Kitchen remodel": 2, "Fence repair": 1}
    # "Newest" is newest on the marketplace: by publication time (Stage 3.14).
    for _p in db.query(_Project).all():
        _p.published_at = datetime.utcnow() - timedelta(minutes=_offsets_minutes_ago[_p.title])
    db.commit()

    r = service_provider_client.get("/service-provider/feed")
    check("unfiltered feed returns all 3 open projects", len(r.json()) == 3)

    r = service_provider_client.get("/service-provider/feed", params={"trade": "roof"})
    check("trade filter (partial, case-insensitive) matches Roofing", len(r.json()) == 1 and r.json()[0]["trade"] == "Roofing")

    r = service_provider_client.get("/service-provider/feed", params={"trade": "electrical"})
    check("trade filter with no matches returns empty list", len(r.json()) == 0)

    r = service_provider_client.get("/service-provider/feed", params={"search": "Maple"})
    check("search matches title (never the exact address)", len(r.json()) == 1)

    r = service_provider_client.get("/service-provider/feed", params={"search": "cedar fence"})
    check("search matches description", len(r.json()) == 1 and r.json()[0]["title"] == "Fence repair")

    r = service_provider_client.get("/service-provider/feed", params={"search": "nonexistent keyword xyz"})
    check("search with no matches returns empty list", len(r.json()) == 0)

    r = service_provider_client.get("/service-provider/feed", params={"sort": "newest"})
    check("sort=newest returns most recently published first", r.json()[0]["title"] == "Fence repair")

    r = service_provider_client.get("/service-provider/feed")
    check("default sort is by deadline ascending (all same deadline here, so just check 3 results)", len(r.json()) == 3)

    r = service_provider_client.get("/service-provider/feed/trades")
    check("distinct trades endpoint returns 200", r.status_code == 200)
    check("distinct trades returns all 3 trades sorted", r.json() == sorted(["Roofing", "Carpentry", "Fencing"]))

    # unauthenticated / wrong-role access rejected
    r = owner_client.get("/service-provider/feed/trades")
    check("owner cannot access service provider feed/trades", r.status_code == 403)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass7_lifecycle():
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    from app.auth.security import hash_password
    from app.models.service_provider import ServiceProviderProfile
    from app.models.document import ServiceProviderDocument
    from app.models.enums import DocumentStatus, ProjectStatus, UserRole
    from app.models.project import Project
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
        json={"email": "c1@example.com", "password": "password123", "full_name": "C1", "role": "service_provider", "company_name": "Acme"},
    )
    service_provider_id = r.json()["id"]

    # fully activate the service provider: approve docs, approve profile, grant override
    for doc in db.query(ServiceProviderDocument).filter_by(service_provider_id=service_provider_id).all():
        doc.status = DocumentStatus.approved
    db.commit()
    admin_client.post(f"/admin/review/service-providers/{service_provider_id}/approve")
    admin_client.post(f"/admin/service-providers/{service_provider_id}/payment-override", json={"reason": "test activation"})

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()
    past = (datetime.utcnow() - timedelta(hours=1)).isoformat()


    # ---------- create_project validation ----------
    r = owner_client.post("/projects", data={"title": "T", "address": "A", "bid_deadline": future, "tender_type": "bogus"})
    check("invalid tender_type rejected", r.status_code == 400)

    r = owner_client.post("/projects", data={"title": "T", "address": "A", "bid_deadline": future, "status": "awarded"})
    check("invalid creation status rejected", r.status_code == 400)

    r = owner_client.post("/projects", data={"title": "T", "address": "A", "bid_deadline": past, "status": "open"})
    check("open project with past deadline rejected", r.status_code == 400)


    # ---------- draft lifecycle ----------
    r = owner_client.post(
        "/projects", data={"title": "Kitchen remodel", "address": "123 Main St", "bid_deadline": future, "status": "draft", "tender_type": "sealed"}
    )
    check("draft project created", r.status_code == 201 and r.json()["status"] == "draft")
    check("tender_type persisted as sealed", r.json()["tender_type"] == "sealed")
    check("tender_type not locked yet", r.json()["tender_type_locked"] is False)
    project_id = r.json()["id"]

    r = service_provider_client.get(f"/projects/{project_id}")
    check("draft project invisible to service_provider", r.status_code == 404)

    r = service_provider_client.get("/service-provider/feed")
    check("draft project absent from feed", all(p["id"] != project_id for p in r.json()["items"]))

    # non-owner can't publish
    r = service_provider_client.post(f"/owner/projects/{project_id}/publish")
    check("non-owner cannot publish (403, wrong role)", r.status_code == 403)

    r = owner_client.post(f"/owner/projects/{project_id}/publish")
    check("owner publishes draft", r.status_code == 200 and r.json()["status"] == "open")

    r = owner_client.post(f"/owner/projects/{project_id}/publish")
    check("re-publishing an already-open project rejected", r.status_code == 400)

    r = service_provider_client.get(f"/projects/{project_id}")
    check("published project now visible to service_provider", r.status_code == 200)


    # ---------- tender_type locking on first bid ----------
    r = service_provider_client.post(f"/projects/{project_id}/offers", json={"amount": "1000.00"})
    check("bid submitted", r.status_code == 200)

    r = owner_client.get(f"/projects/{project_id}")
    check("tender_type_locked flips true after first bid", r.json()["tender_type_locked"] is True)


    # ---------- award requires closed/under_evaluation, not open ----------
    offers = owner_client.get(f"/owner/projects/{project_id}/offers").json()
    offer_id = offers[0]["id"]

    r = owner_client.post(f"/owner/projects/{project_id}/offers/{offer_id}/approve")
    check("awarding while still open is rejected", r.status_code == 400)

    # This tender is sealed and has a bid: closing it early would unseal that bid, so it is refused
    # (audit remediation R1). It closes when its deadline passes instead. Early close of an
    # owner-visible tender is still exercised below (project2) and in the R1 regression tests.
    r = owner_client.post(f"/owner/projects/{project_id}/close")
    check("owner cannot close a sealed tender early", r.status_code == 400)

    from app.models.project import Project as _Project

    db.get(_Project, project_id).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner_client.get("/owner/projects")  # lazy deadline sync, exactly as production does on any read
    r = owner_client.get(f"/projects/{project_id}")
    check("sealed tender closes when its deadline passes", r.json()["status"] == "closed")

    r = owner_client.post(f"/owner/projects/{project_id}/close")
    check("closing an already-closed project rejected", r.status_code == 400)

    r = owner_client.post(f"/owner/projects/{project_id}/start-evaluation")
    check("owner starts evaluation", r.status_code == 200 and r.json()["status"] == "under_evaluation")

    r = owner_client.post(f"/owner/projects/{project_id}/offers/{offer_id}/approve")
    check("award succeeds from under_evaluation", r.status_code == 200 and r.json()["status"] == "awarded")

    r = owner_client.post(f"/owner/projects/{project_id}/cancel")
    check("cannot cancel an awarded project", r.status_code == 400)


    # ---------- no-award path ----------
    r = owner_client.post(
        "/projects", data={"title": "Fence repair", "address": "456 Oak Ave", "bid_deadline": future, "status": "open"}
    )
    project2_id = r.json()["id"]
    owner_client.post(f"/owner/projects/{project2_id}/close")

    r = owner_client.post(f"/owner/projects/{project2_id}/no-award")
    check("no-award from closed succeeds", r.status_code == 200 and r.json()["status"] == "no_award")

    r = owner_client.post(f"/owner/projects/{project2_id}/no-award")
    check("no-award on an already-no_award project rejected", r.status_code == 400)


    # ---------- cancel path ----------
    r = owner_client.post(
        "/projects", data={"title": "Deck build", "address": "789 Pine Rd", "bid_deadline": future, "status": "open"}
    )
    project3_id = r.json()["id"]
    r = owner_client.post(f"/owner/projects/{project3_id}/cancel")
    check("cancel from open succeeds", r.status_code == 200 and r.json()["status"] == "canceled")

    # Once offers have closed, only providers who took part can open it
    # (this provider never bid on project3).
    r = service_provider_client.get(f"/projects/{project3_id}")
    check("canceled project hidden from a provider who never bid", r.status_code == 404)


    # ---------- auto-expire / auto-close on deadline (sync_expired_projects) ----------
    # Project with a live bid, deadline forced into the past directly in the DB.
    r = owner_client.post(
        "/projects", data={"title": "Bathroom reno", "address": "1 Elm St", "bid_deadline": future, "status": "open"}
    )
    project4_id = r.json()["id"]
    service_provider_client.post(f"/projects/{project4_id}/offers", json={"amount": "500.00"})

    p4 = db.get(Project, project4_id)
    p4.bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    r = owner_client.get("/owner/projects")
    synced = next(p for p in r.json() if p["id"] == project4_id)
    check("project with a live bid auto-closes past deadline", synced["status"] == "closed")

    # Project with zero bids, deadline forced into the past -> expired.
    r = owner_client.post(
        "/projects", data={"title": "Gutter cleaning", "address": "2 Elm St", "bid_deadline": future, "status": "open"}
    )
    project5_id = r.json()["id"]
    p5 = db.get(Project, project5_id)
    p5.bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    r = owner_client.get("/owner/projects")
    synced5 = next(p for p in r.json() if p["id"] == project5_id)
    check("project with zero bids auto-expires past deadline", synced5["status"] == "expired")

    # Same sync path is reachable via the service provider feed and via GET /projects/{id}
    r = owner_client.post(
        "/projects", data={"title": "Siding repair", "address": "3 Elm St", "bid_deadline": future, "status": "open"}
    )
    project6_id = r.json()["id"]
    p6 = db.get(Project, project6_id)
    p6.bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    r = service_provider_client.get("/service-provider/feed")
    check("expired project no longer in feed after sync", all(p["id"] != project6_id for p in r.json()["items"]))

    r = admin_client.get(f"/projects/{project6_id}")  # admin can always view regardless of status
    check("admin sees synced expired status via single-project GET", r.status_code == 200 and r.json()["status"] == "expired")


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

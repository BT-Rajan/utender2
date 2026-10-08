from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app

from tests.stage7_helpers import complete_transaction


def test_pass17_security_hardening():
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    from app.auth.security import hash_password
    from app.models.document import ServiceProviderDocument
    from app.models.enums import DocumentStatus, UserRole, VerificationStatus
    from app.models.review import Review
    from app.models.user import User

    db = db_module.SessionLocal()

    admin = User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin")
    db.add(admin)
    db.commit()
    admin_client = TestClient(app)
    admin_client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})


    def make_owner(email):
        client = TestClient(app)
        r = client.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "O", "role": "owner"})
        from app.models.owner import OwnerProfile
        db.get(OwnerProfile, r.json()["id"]).verification_status = VerificationStatus.approved
        db.commit()
        return client


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
        admin_client.post(f"/admin/service-providers/{cid}/payment-override", json={"reason": "test activation"})
        return client, cid


    future = (datetime.utcnow() + timedelta(days=7)).isoformat()

    owner1 = make_owner("owner1@example.com")
    owner2 = make_owner("owner2@example.com")
    c1, c1_id = make_active_service_provider("c1@example.com", "Acme")
    c2, c2_id = make_active_service_provider("c2@example.com", "BuildCo")


    # =================================================================
    # FIX 1: review IDOR — an owner can no longer attach a review to a
    # service provider who wasn't actually awarded the project.
    # =================================================================

    r = owner1.post("/projects", data={"title": "Roof job", "address": "1 Main St", "bid_deadline": future, "status": "open"})
    project_id = r.json()["id"]
    r = c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00"})
    offer1_id = r.json()["id"]
    owner1.post(f"/owner/projects/{project_id}/close")
    owner1.post(f"/owner/projects/{project_id}/offers/{offer1_id}/approve")
    # Stage 8.1: a review rests on completed work, not on the award alone.
    r = owner1.post("/owner/reviews", json={"project_id": project_id, "service_provider_id": c1_id, "rating": 5})
    check("reviewing an awarded but not yet completed transaction is rejected", r.status_code == 400)
    complete_transaction(owner1, c1, project_id)

    # Attempt: forge a review naming c2 (who never bid on this project) as the reviewed service provider.
    r = owner1.post("/owner/reviews", json={"project_id": project_id, "service_provider_id": c2_id, "rating": 1, "comment": "attack"})
    check("forged review request is accepted (still succeeds)", r.status_code == 200)
    check("but the review is attributed to the ACTUAL winner (c1), not the forged target (c2)", r.json()["service_provider_id"] == c1_id)

    # c2's public profile is completely unaffected by the attack.
    r = c2.get("/service-provider/profile")
    check("c2's review_count is untouched by the forged review attempt", r.json()["review_count"] == 0)

    # c1's profile DID get the legitimate review.
    r = c1.get("/service-provider/profile")
    check("c1 (the real winner) received the review", r.json()["review_count"] == 1)

    review_row = db.query(Review).filter_by(project_id=project_id).first()
    check("the persisted Review row's service_provider_id is the real winner, not the forged one", review_row.service_provider_id == c1_id)

    # A project with no award record at all cannot be reviewed regardless of payload.
    r2 = owner2.post("/projects", data={"title": "Unawarded job", "address": "9 Nowhere Ave", "bid_deadline": future, "status": "open"})
    unawarded_id = r2.json()["id"]
    r = owner2.post("/owner/reviews", json={"project_id": unawarded_id, "service_provider_id": c1_id, "rating": 5})
    check("reviewing a project with no AwardRecord is rejected", r.status_code == 400)


    # =================================================================
    # FIX 2: clarifications leak bidder identity on a sealed, open tender
    # =================================================================

    r = owner1.post("/projects", data={"title": "Sealed job", "address": "2 Oak Ave", "bid_deadline": future, "status": "open", "tender_type": "sealed"})
    sealed_id = r.json()["id"]
    c1.post(f"/projects/{sealed_id}/offers", json={"amount": "9000.00"})
    c1.post(f"/projects/{sealed_id}/clarifications", json={"question": "What's the material spec?", "shared_with_all": True})

    r = owner1.get(f"/projects/{sealed_id}/clarifications")
    check("owner CAN see the question exists while sealed+open", len(r.json()) == 1)
    q = r.json()[0]
    check("owner does NOT see service_provider_id while sealed+open", q["service_provider_id"] is None)
    check("owner does NOT see service_provider_company_name while sealed+open", q["service_provider_company_name"] is None)
    check("question text itself is still visible (not over-redacted)", q["question"] == "What's the material spec?")

    # admin is NOT subject to the same redaction (platform oversight)
    r = admin_client.get(f"/projects/{sealed_id}/clarifications")
    check("admin sees full service provider identity even while sealed", r.json()[0]["service_provider_id"] == c1_id)

    # the asking service provider sees their OWN identity fields fine (not self-redacted)
    r = c1.get(f"/projects/{sealed_id}/clarifications")
    check("the asking service provider sees their own service_provider_id on their own question", r.json()[0]["service_provider_id"] == c1_id)

    # owner answers -> the ANSWER response itself is also redacted
    q_id = q["id"]
    r = owner1.post(f"/projects/{sealed_id}/clarifications/{q_id}/answer", json={"answer": "Grade A steel"})
    check("owner's answer succeeds", r.status_code == 200)
    check("the answer response itself does not reveal service provider identity while sealed", r.json()["service_provider_id"] is None)

    # once bidding closes, the seal lifts and identity is visible again. A sealed tender closes
    # only when its deadline passes (an owner can't close it early -- audit remediation R1).
    from app.models.project import Project as _Project

    db.get(_Project, sealed_id).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner1.get("/owner/projects")  # lazy deadline sync, exactly as production does on any read
    r = owner1.get(f"/projects/{sealed_id}/clarifications")
    check("after closing, owner now sees service provider identity on the same question", r.json()[0]["service_provider_id"] == c1_id)


    # =================================================================
    # Broader adversarial sweep: IDOR / role-escalation spot checks
    # =================================================================

    # Owner cannot view or act on another owner's project.
    r = owner2.get(f"/owner/projects/{project_id}/offers")
    check("owner2 cannot list offers on owner1's project (404)", r.status_code == 404)
    r = owner2.post(f"/owner/projects/{project_id}/close")
    check("owner2 cannot close owner1's project (404)", r.status_code == 404)
    r = owner2.post(f"/owner/projects/{project_id}/offers/{offer1_id}/approve")
    check("owner2 cannot approve an offer on owner1's project (404)", r.status_code == 404)

    # A service provider cannot withdraw or read another service provider's offer.
    r = owner1.post("/projects", data={"title": "IDOR test job", "address": "3 Pine Rd", "bid_deadline": future, "status": "open"})
    idor_project_id = r.json()["id"]
    c1.post(f"/projects/{idor_project_id}/offers", json={"amount": "100.00"})
    r = c2.get(f"/projects/{idor_project_id}/offers/mine")
    check("c2's 'my offer' on a project only c1 bid on is null, not c1's offer", r.json() is None)
    r = c2.post(f"/projects/{idor_project_id}/offers/withdraw")
    check("c2 cannot withdraw an offer they never placed (404)", r.status_code == 404)

    # A service provider cannot answer clarifications (owner-only action).
    r = c1.post(f"/projects/{idor_project_id}/clarifications", json={"question": "test"})
    q2_id = r.json()["id"]
    r = c2.post(f"/projects/{idor_project_id}/clarifications/{q2_id}/answer", json={"answer": "hijack"})
    check("a service provider cannot answer a clarification (role-gated, 403)", r.status_code == 403)

    # Non-admin cannot reach any /admin/* route.
    r = owner1.get("/admin/service-providers")
    check("owner blocked from /admin/service-providers (403)", r.status_code == 403)
    r = c1.get("/admin/review/queue")
    check("service_provider blocked from /admin/review/queue (403)", r.status_code == 403)
    r = owner1.post(f"/admin/service-providers/{c1_id}/suspend", json={"suspended": True})
    check("owner cannot suspend a service provider (403)", r.status_code == 403)

    # A service provider cannot amend a project they don't own.
    r = c1.patch(f"/projects/{idor_project_id}", json={"title": "Hijacked"})
    check("service_provider cannot amend a project (404, ownership check wins over role)", r.status_code == 404)

    # A suspended service provider is fully locked out despite an active override.
    admin_client.post(f"/admin/service-providers/{c1_id}/suspend", json={"suspended": True})
    r = c1.get("/service-provider/feed")
    check("suspended service provider blocked from feed even with payment override active", r.status_code == 403)
    r = c1.post(f"/projects/{idor_project_id}/offers", json={"amount": "50.00"})
    check("suspended service provider blocked from bidding even with payment override active", r.status_code == 403)
    admin_client.post(f"/admin/service-providers/{c1_id}/suspend", json={"suspended": False})


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

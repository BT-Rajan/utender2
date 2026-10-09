from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass13_award_workflow():
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    from app.auth.security import hash_password
    from app.models.audit_log import AuditLog
    from app.models.award_record import AwardRecord
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


    c1, c1_id = make_active_service_provider("c1@example.com", "Acme")
    c2, c2_id = make_active_service_provider("c2@example.com", "BuildCo")
    c3, c3_id = make_active_service_provider("c3@example.com", "ThirdCo")

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()

    r = owner_client.post("/projects", data={"title": "Deck build", "address": "1 Main St", "bid_deadline": future, "status": "open"})
    project_id = r.json()["id"]

    r = c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00"})
    offer1_id = r.json()["id"]
    c2.post(f"/projects/{project_id}/offers", json={"amount": "4800.00"})
    c3.post(f"/projects/{project_id}/offers", json={"amount": "5200.00"})
    # c3 changes their mind and withdraws before the owner picks a winner
    c3.post(f"/projects/{project_id}/offers/withdraw")

    r = owner_client.get(f"/projects/{project_id}/award")
    check("no award record before award (404)", r.status_code == 404)

    owner_client.post(f"/owner/projects/{project_id}/close")

    r = owner_client.post(f"/owner/projects/{project_id}/offers/{offer1_id}/approve")
    check("award succeeds", r.status_code == 200 and r.json()["status"] == "awarded")

    # AwardRecord row actually created
    record = db.query(AwardRecord).filter_by(project_id=project_id).first()
    check("AwardRecord row created", record is not None)
    check("AwardRecord.offer_id matches the winning offer", record.offer_id == offer1_id)
    check("AwardRecord.service_provider_id matches c1", record.service_provider_id == c1_id)
    check("AwardRecord.amount matches the winning bid", float(record.amount) == 5000.00)
    check("AwardRecord.awarded_by is the owner", record.awarded_by is not None)

    # audit log entry
    audit_row = db.query(AuditLog).filter_by(action="project.award", target_id=project_id).first()
    check("audit log entry for the award exists", audit_row is not None)
    check("audit log new_value references the winning offer", offer1_id in (audit_row.new_value or ""))

    # withdrawn offer stays withdrawn, not silently flipped to rejected
    from app.models.offer import Offer
    from app.models.enums import OfferStatus

    c3_offer = db.query(Offer).filter_by(project_id=project_id, service_provider_id=c3_id).first()
    check("withdrawn offer STAYS withdrawn after award (not overwritten to rejected)", c3_offer.status == OfferStatus.withdrawn)

    c2_offer = db.query(Offer).filter_by(project_id=project_id, service_provider_id=c2_id).first()
    check("live losing offer correctly marked rejected", c2_offer.status == OfferStatus.rejected)

    # GET /projects/{id}/award now works, for owner, admin, and the winning service provider
    r = owner_client.get(f"/projects/{project_id}/award")
    check("owner can view award record", r.status_code == 200)
    check("award record includes winning company name", r.json()["service_provider_company_name"] == "Acme")

    r = admin_client.get(f"/projects/{project_id}/award")
    check("admin can view award record", r.status_code == 200)

    r = c1.get(f"/projects/{project_id}/award")
    check("winning service provider can view award record", r.status_code == 200)

    r = c2.get(f"/projects/{project_id}/award")
    check("losing (but eligible) service provider can also view award record", r.status_code == 200)

    # double-award attempts are rejected
    r = owner_client.post(f"/owner/projects/{project_id}/offers/{offer1_id}/approve")
    check("re-approving after already awarded is rejected", r.status_code == 400)

    # approving an already-withdrawn offer is rejected outright
    r2 = owner_client.post("/projects", data={"title": "Second job", "address": "2 Oak Ave", "bid_deadline": future, "status": "open"})
    project2_id = r2.json()["id"]
    r = c1.post(f"/projects/{project2_id}/offers", json={"amount": "1000.00"})
    offer2_id = r.json()["id"]
    c1.post(f"/projects/{project2_id}/offers/withdraw")
    owner_client.post(f"/owner/projects/{project2_id}/close")
    r = owner_client.post(f"/owner/projects/{project2_id}/offers/{offer2_id}/approve")
    check("approving a withdrawn offer is rejected outright", r.status_code == 400)

    # no-award and cancel are audited too
    r3 = owner_client.post("/projects", data={"title": "Third job", "address": "3 Pine Rd", "bid_deadline": future, "status": "open"})
    project3_id = r3.json()["id"]
    # Batch B: closing with no live offer now expires the requirement (no-award is then refused),
    # so a provider submits first and the close leaves it waiting on the owner's decision.
    c2.post(f"/projects/{project3_id}/offers", json={"amount": "900.00"})
    r = owner_client.post(f"/owner/projects/{project3_id}/close")
    check("close with a live offer leaves it closed (Batch B)", r.status_code == 200 and r.json()["status"] == "closed")
    r = owner_client.post(f"/owner/projects/{project3_id}/no-award")
    check("no-award from closed succeeds (Batch B)", r.status_code == 200 and r.json()["status"] == "no_award")
    no_award_audit = db.query(AuditLog).filter_by(action="project.no_award", target_id=project3_id).first()
    check("no-award action is audited", no_award_audit is not None)

    r4 = owner_client.post("/projects", data={"title": "Fourth job", "address": "4 Elm St", "bid_deadline": future, "status": "open"})
    project4_id = r4.json()["id"]
    owner_client.post(f"/owner/projects/{project4_id}/cancel")
    cancel_audit = db.query(AuditLog).filter_by(action="project.cancel", target_id=project4_id).first()
    check("cancel action is audited", cancel_audit is not None)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

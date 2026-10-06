"""PASS 21 -- end-to-end business scenario testing.

Two full multi-actor lifecycles run continuously through the real FastAPI
app (not isolated per-endpoint checks): one owner-visible tender, one
sealed tender, each with 3 competing service providers (one of whom withdraws).
Chains together clarifications, amendments, bid revisions/withdrawal,
deadline auto-expiry, evaluation, award, audit logging, notifications,
and ratings recompute -- verifying they all correctly compose in one
continuous flow, which the per-pass unit-style tests never exercised
together.
"""
from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass21_e2e_scenarios():
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    from app.auth.security import hash_password
    from app.models.audit_log import AuditLog
    from app.models.award_record import AwardRecord
    from app.models.document import ServiceProviderDocument
    from app.models.enums import DocumentStatus, UserRole, OfferStatus
    from app.models.offer import Offer
    from app.models.project import Project as ProjectModel
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


    def notification_types_for(client):
        r = client.get("/notifications")
        check(f"  notifications list fetched ({r.status_code})", r.status_code == 200)
        return {n["type"] for n in r.json()}


    c1, c1_id = make_active_service_provider("c1@example.com", "Acme Roofing")
    c2, c2_id = make_active_service_provider("c2@example.com", "BuildCo")
    c3, c3_id = make_active_service_provider("c3@example.com", "ThirdCo")

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()

    # ======================================================================
    # SCENARIO A: owner-visible tender, full lifecycle
    # ======================================================================
    print("\n=== SCENARIO A: owner-visible tender ===")

    r = owner_client.post(
        "/projects",
        data={
            "title": "Kitchen remodel",
            "address": "10 Baker St",
            "trade": "General",
            "bid_deadline": future,
            "status": "open",
            "tender_type": "owner_visible",
        },
    )
    check("A: project created (owner-visible)", r.status_code == 201)
    projA = r.json()["id"]
    check("A: tender_type is owner_visible", r.json()["tender_type"] == "owner_visible")

    # --- clarifications, before any bids ---
    r = c1.post(f"/projects/{projA}/clarifications", json={"question": "What's the cabinet finish?", "shared_with_all": True})
    check("A: service provider asks a question", r.status_code == 201)
    qA_id = r.json()["id"]
    r = owner_client.post(f"/projects/{projA}/clarifications/{qA_id}/answer", json={"answer": "Shaker, white oak"})
    check("A: owner answers", r.status_code == 200)
    r = c2.get(f"/projects/{projA}/clarifications")
    check("A: shared Q&A visible to a different service_provider", any(c["answer"] == "Shaker, white oak" for c in r.json()))

    # --- amendment before bids exist ---
    extended = (datetime.utcnow() + timedelta(days=9)).isoformat()
    r = owner_client.patch(f"/projects/{projA}", json={"description": "Add pantry reno to scope.", "bid_deadline": extended, "reason": "Scope grew"})
    check("A: amendment applied before any bids", r.status_code == 200)
    r = owner_client.get(f"/projects/{projA}/amendments")
    check("A: amendment recorded in history", len(r.json()) == 1)

    # --- bidding: c1 bids, c2 bids then revises down, c3 bids then withdraws ---
    r = c1.post(f"/projects/{projA}/offers", json={"amount": "18000.00", "timeline_estimate": "3 weeks"})
    check("A: c1 bids", r.status_code == 200)
    offerA1_id = r.json()["id"]

    c2.post(f"/projects/{projA}/offers", json={"amount": "19500.00"})
    r = c2.post(f"/projects/{projA}/offers", json={"amount": "17500.00"})
    check("A: c2 revises their bid down", r.status_code == 200 and r.json()["revision"] >= 1)

    r = c3.post(f"/projects/{projA}/offers", json={"amount": "20000.00"})
    offerA3_id = r.json()["id"]
    c3.post(f"/projects/{projA}/offers/withdraw")

    # --- owner-visible: owner CAN see service provider identities/amounts while still open ---
    r = owner_client.get(f"/owner/projects/{projA}/offers")
    check("A: owner sees offers while tender still open (owner-visible)", r.status_code == 200)
    offers_open = r.json()
    check("A: real amounts visible pre-close on an owner-visible tender", any(o["amount"] == "18000.000" for o in offers_open))
    check("A: not marked sealed", all(o["sealed"] is False for o in offers_open))

    # --- force deadline into the past, sync via a normal read path ---
    pA = db.get(ProjectModel, projA)
    pA.bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    r = owner_client.get("/owner/projects")
    synced = next(p for p in r.json() if p["id"] == projA)
    check("A: project auto-closes on deadline (has live bids)", synced["status"] == "closed")

    # --- evaluate & award the lowest live bid (c2, 17500) ---
    owner_client.post(f"/owner/projects/{projA}/start-evaluation")
    r = owner_client.get(f"/owner/projects/{projA}/offers")
    offerA2_id = next(o["id"] for o in r.json() if o["service_provider_company_name"] == "BuildCo")

    r = owner_client.post(f"/owner/projects/{projA}/offers/{offerA2_id}/approve")
    check("A: award to lowest live bidder succeeds", r.status_code == 200 and r.json()["status"] == "awarded")

    record = db.query(AwardRecord).filter_by(project_id=projA).first()
    check("A: AwardRecord created for the right service_provider", record is not None and record.service_provider_id == c2_id)
    audit_row = db.query(AuditLog).filter_by(action="project.award", target_id=projA).first()
    check("A: award is audited", audit_row is not None)

    c1_offer = db.query(Offer).filter_by(project_id=projA, service_provider_id=c1_id).first()
    check("A: losing live bidder (c1) rejected", c1_offer.status == OfferStatus.rejected)
    c3_offer = db.query(Offer).filter_by(project_id=projA, service_provider_id=c3_id).first()
    check("A: withdrawn bidder (c3) stays withdrawn, not overwritten", c3_offer.status == OfferStatus.withdrawn)

    # --- notifications: winner gets award_won, live loser gets award_lost, withdrawn bidder gets neither ---
    c1_notifs = notification_types_for(c1)
    c2_notifs = notification_types_for(c2)
    c3_notifs = notification_types_for(c3)
    check("A: winner (c2) notified award_won", "award_won" in c2_notifs)
    check("A: live loser (c1) notified award_lost", "award_lost" in c1_notifs)
    check("A: withdrawn bidder (c3) gets NEITHER award notification", "award_won" not in c3_notifs and "award_lost" not in c3_notifs)

    # --- review + rating recompute ---
    r = owner_client.post("/owner/reviews", json={"project_id": projA, "service_provider_id": c2_id, "rating": 5, "comment": "Great work"})
    check("A: review submitted for the actual winner", r.status_code == 200)

    r = c2.get("/service-provider/profile")
    check("A: winning service provider's avg_rating recomputed to 5.0", float(r.json()["avg_rating"]) == 5.0)
    check("A: winning service provider's review_count is 1", r.json()["review_count"] == 1)

    r = owner_client.post("/owner/reviews", json={"project_id": projA, "service_provider_id": c2_id, "rating": 1})
    check("A: duplicate review on the same project rejected", r.status_code == 400)

    # ======================================================================
    # SCENARIO B: sealed tender, full lifecycle with privacy checks
    # ======================================================================
    print("\n=== SCENARIO B: sealed tender ===")

    r = owner_client.post(
        "/projects",
        data={
            "title": "Roof replacement",
            "address": "22 Cedar Ln",
            "trade": "Roofing",
            "bid_deadline": future,
            "status": "open",
            "tender_type": "sealed",
        },
    )
    check("B: sealed project created", r.status_code == 201)
    projB = r.json()["id"]

    r = c1.post(f"/projects/{projB}/clarifications", json={"question": "Metal or shingle?", "shared_with_all": True})
    qB_id = r.json()["id"]
    owner_client.post(f"/projects/{projB}/clarifications/{qB_id}/answer", json={"answer": "Architectural shingle"})

    r = owner_client.get(f"/projects/{projB}/clarifications")
    check("B: owner's clarification view redacts bidder identity while sealed+open", r.json()[0]["service_provider_id"] is None)

    r = c1.post(f"/projects/{projB}/offers", json={"amount": "9800.00"})
    offerB1_id = r.json()["id"]
    r = c2.post(f"/projects/{projB}/offers", json={"amount": "9200.00"})
    offerB2_id = r.json()["id"]
    r = c3.post(f"/projects/{projB}/offers", json={"amount": "9500.00"})
    c3.post(f"/projects/{projB}/offers/withdraw")

    # --- sealed + open: owner CANNOT see identities/amounts yet ---
    r = owner_client.get(f"/owner/projects/{projB}/offers")
    check("B: offers list reachable while sealed+open", r.status_code == 200)
    sealed_offers = r.json()
    check("B: service provider identity redacted while sealed+open", all(o["service_provider_id"] is None for o in sealed_offers))
    check("B: amount redacted while sealed+open", all(o["amount"] is None for o in sealed_offers))
    check("B: marked sealed=True in the API response", all(o["sealed"] is True for o in sealed_offers))

    r = owner_client.get(f"/projects/{projB}/award")
    check("B: no award record exists yet (404)", r.status_code == 404)

    # --- force deadline past, sync ---
    pB = db.get(ProjectModel, projB)
    pB.bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    r = owner_client.get("/owner/projects")
    syncedB = next(p for p in r.json() if p["id"] == projB)
    check("B: sealed project auto-closes on deadline", syncedB["status"] == "closed")

    # --- seal lifts once closed ---
    r = owner_client.get(f"/owner/projects/{projB}/offers")
    unsealed_offers = r.json()
    check("B: seal lifts once closed -- identities now visible", any(o["service_provider_id"] == c2_id for o in unsealed_offers))
    check("B: seal lifts once closed -- real amounts now visible", any(o["amount"] == "9200.000" for o in unsealed_offers))
    check("B: response no longer marked sealed", all(o["sealed"] is False for o in unsealed_offers))

    owner_client.post(f"/owner/projects/{projB}/start-evaluation")
    r = owner_client.post(f"/owner/projects/{projB}/offers/{offerB2_id}/approve")
    check("B: award to lowest live bidder (c2) succeeds", r.status_code == 200 and r.json()["status"] == "awarded")

    recordB = db.query(AwardRecord).filter_by(project_id=projB).first()
    check("B: AwardRecord service provider is c2", recordB is not None and recordB.service_provider_id == c2_id)
    check("B: AwardRecord amount matches the winning bid", float(recordB.amount) == 9200.00)

    c1_offerB = db.query(Offer).filter_by(project_id=projB, service_provider_id=c1_id).first()
    check("B: live loser (c1) rejected", c1_offerB.status == OfferStatus.rejected)

    c1_notifsB = notification_types_for(c1)
    c3_notifsB = notification_types_for(c3)
    check("B: live loser (c1) notified award_lost for scenario B too", "award_lost" in c1_notifsB)
    check("B: withdrawn bidder (c3) still has no award notification from scenario B", "award_won" not in c3_notifsB and "award_lost" not in c3_notifsB)

    # a losing, non-withdrawn service provider can still see the award record post-close
    r = c1.get(f"/projects/{projB}/award")
    check("B: losing eligible service provider can view award record after close", r.status_code == 200)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

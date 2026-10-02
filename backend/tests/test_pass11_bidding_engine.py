from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass11_bidding_engine():
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    from app.auth.security import hash_password
    from app.models.document import ContractorDocument
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


    def make_active_contractor(email, company):
        client = TestClient(app)
        r = client.post(
            "/auth/signup",
            json={"email": email, "password": "password123", "full_name": "C", "role": "contractor", "company_name": company},
        )
        cid = r.json()["id"]
        for doc in db.query(ContractorDocument).filter_by(contractor_id=cid).all():
            doc.status = DocumentStatus.approved
        db.commit()
        admin_client.post(f"/admin/review/contractors/{cid}/approve")
        admin_client.post(f"/admin/contractors/{cid}/payment-override", json={"reason": "test activation"})
        return client, cid


    c1, c1_id = make_active_contractor("c1@example.com", "Acme")
    c2, c2_id = make_active_contractor("c2@example.com", "BuildCo")

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()


    # ---------- bid revision history ----------
    r = owner_client.post("/projects", data={"title": "Open bid job", "address": "1 Main St", "bid_deadline": future, "status": "open", "tender_type": "owner_visible"})
    open_project_id = r.json()["id"]

    r = c1.post(f"/projects/{open_project_id}/offers", json={"amount": "1000.00", "message": "first pass"})
    check("initial bid submitted at revision 1", r.status_code == 200 and r.json()["revision"] == 1)

    r = c1.get(f"/projects/{open_project_id}/offers/mine/history")
    check("no history rows yet before any edit", r.status_code == 200 and len(r.json()) == 0)

    r = c1.post(f"/projects/{open_project_id}/offers", json={"amount": "950.00", "message": "revised down"})
    check("bid revised, now revision 2 with the new amount", r.status_code == 200 and r.json()["revision"] == 2 and float(r.json()["amount"]) == 950.00)

    r = c1.get(f"/projects/{open_project_id}/offers/mine/history")
    history = r.json()
    check("exactly one snapshot recorded after one edit", len(history) == 1)
    check("snapshot captured the ORIGINAL pre-edit amount (1000), not the new one", float(history[0]["amount"]) == 1000.00)
    check("snapshot revision_number matches the pre-edit revision (1)", history[0]["revision_number"] == 1)
    check("snapshot captured the original message", history[0]["message"] == "first pass")

    r = c1.post(f"/projects/{open_project_id}/offers", json={"amount": "900.00"})
    check("second edit -> revision 3", r.status_code == 200 and r.json()["revision"] == 3)

    r = c1.get(f"/projects/{open_project_id}/offers/mine/history")
    history = r.json()
    check("two snapshots now recorded", len(history) == 2)
    check("snapshots are in revision order 1, 2", [h["revision_number"] for h in history] == [1, 2])
    check("second snapshot has the amount from between the two edits (950)", float(history[1]["amount"]) == 950.00)

    # withdraw also snapshots
    r = c1.post(f"/projects/{open_project_id}/offers/withdraw")
    check("withdraw succeeds", r.status_code == 200 and r.json()["status"] == "withdrawn")
    r = c1.get(f"/projects/{open_project_id}/offers/mine/history")
    check("withdrawal also recorded a snapshot (3 total now)", len(r.json()) == 3)

    r = c1.post(f"/projects/{open_project_id}/offers/withdraw")
    check("withdrawing an already-withdrawn offer is rejected", r.status_code == 400)

    # owner sees revision count for a non-sealed project (no redaction)
    r = c2.post(f"/projects/{open_project_id}/offers", json={"amount": "1200.00"})
    r = owner_client.get(f"/owner/projects/{open_project_id}/offers")
    c2_offer = next(o for o in r.json() if o["contractor_id"] == c2_id)
    check("owner sees real contractor_id on owner-visible tender", c2_offer["contractor_id"] == c2_id)
    check("owner sees real amount on owner-visible tender", float(c2_offer["amount"]) == 1200.00)
    check("sealed flag is False on owner-visible tender", c2_offer["sealed"] is False)

    r = owner_client.get(f"/owner/projects/{open_project_id}/offers/{c2_offer['id']}/history")
    check("owner can view offer history on a non-sealed tender", r.status_code == 200)


    # ---------- sealed-bid privacy ----------
    r = owner_client.post("/projects", data={"title": "Sealed job", "address": "2 Oak Ave", "bid_deadline": future, "status": "open", "tender_type": "sealed"})
    sealed_project_id = r.json()["id"]

    c1.post(f"/projects/{sealed_project_id}/offers", json={"amount": "5000.00", "message": "secret bid A"})
    c2.post(f"/projects/{sealed_project_id}/offers", json={"amount": "4500.00", "message": "secret bid B"})

    r = owner_client.get(f"/owner/projects/{sealed_project_id}/offers")
    check("owner sees 2 bids exist while sealed+open", len(r.json()) == 2)
    check("ALL amounts hidden while sealed+open", all(o["amount"] is None for o in r.json()))
    check("ALL contractor_ids hidden while sealed+open", all(o["contractor_id"] is None for o in r.json()))
    check("ALL messages hidden while sealed+open", all(o["message"] is None for o in r.json()))
    check("ALL company names hidden while sealed+open", all(o["contractor_company_name"] is None for o in r.json()))
    check("sealed flag is True on every row", all(o["sealed"] is True for o in r.json()))

    sealed_offer_ids = [o["id"] for o in r.json()]
    r = owner_client.get(f"/owner/projects/{sealed_project_id}/offers/{sealed_offer_ids[0]}/history")
    check("offer history endpoint also blocked while sealed+open", r.status_code == 404)

    # even trying to fetch an offer id "out of band" doesn't leak via history endpoint
    r = owner_client.get(f"/owner/projects/{sealed_project_id}/offers/{sealed_offer_ids[1]}/history")
    check("second sealed offer's history also blocked", r.status_code == 404)

    # contractor still sees their OWN full bid even while sealed
    r = c1.get(f"/projects/{sealed_project_id}/offers/mine")
    check("contractor sees their own amount even on a sealed tender", float(r.json()["amount"]) == 5000.00)

    # once bidding closes, the seal lifts. A sealed tender closes only when its deadline
    # passes -- the owner can no longer close it early (audit remediation R1) -- so expire it.
    from app.models.project import Project as _Project

    db.get(_Project, sealed_project_id).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner_client.get("/owner/projects")  # lazy deadline sync, exactly as production does on any read
    r = owner_client.get(f"/owner/projects/{sealed_project_id}/offers")
    check("after close, amounts are revealed", all(o["amount"] is not None for o in r.json()))
    check("after close, contractor identities are revealed", all(o["contractor_id"] is not None for o in r.json()))
    check("after close, sealed flag is False", all(o["sealed"] is False for o in r.json()))
    revealed_amounts = sorted(float(o["amount"]) for o in r.json())
    check("revealed amounts match what was actually bid", revealed_amounts == [4500.0, 5000.0])

    r = owner_client.get(f"/owner/projects/{sealed_project_id}/offers/{sealed_offer_ids[0]}/history")
    check("offer history now accessible after seal lifts", r.status_code == 200)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

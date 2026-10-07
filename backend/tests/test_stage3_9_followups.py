"""Stage 3.9 follow-ups:
- service categories and governorates as structured, enforceable eligibility;
- a verified provider adding a qualification later without losing access;
- admin offer edits following the same eligibility and response rules;
(the translated reasons are covered in test_stage3_9_provider_eligibility)."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models.document import DocumentRequirement, ServiceProviderDocument
from app.models.enums import DocumentStatus, UserRole, VerificationStatus
from app.models.offer import OfferRevision
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from app.auth.security import hash_password

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat()


def _admin(db) -> TestClient:
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"}).status_code == 200
    return c


def _owner(db) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": "owner@example.com", "password": "password123", "full_name": "N", "role": "owner"})
    c.put("/account/stakeholder", json={"type": "individual"})
    db.get(OwnerProfile, r.json()["id"]).verification_status = VerificationStatus.approved
    db.commit()
    return c


def _provider(db, email: str) -> tuple[TestClient, str]:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": "service_provider"})
    c.put("/account/stakeholder", json={"type": "individual"})
    profile = db.get(ServiceProviderProfile, r.json()["id"])
    profile.company_name = email.split("@")[0]
    profile.payment_override_active = True
    profile.verification_status = VerificationStatus.approved
    db.commit()
    return c, profile.user_id


def test_category_and_governorate_matching(db):
    admin = _admin(db)
    electrical = admin.post("/admin/categories", json={"name": "Electrical"}).json()
    plumbing = admin.post("/admin/categories", json={"name": "Plumbing"}).json()
    assert admin.post("/admin/categories", json={"name": "electrical"}).status_code == 409
    retired = admin.post("/admin/categories", json={"name": "Asbestos removal"}).json()
    admin.patch(f"/admin/categories/{retired['id']}", json={"is_active": False})

    owner = _owner(db)
    assert [c["name"] for c in owner.get("/categories").json()] == ["Electrical", "Plumbing"]
    assert owner.post("/projects", data={"title": "T", "address": "A", "bid_deadline": DEADLINE, "category_id": retired["id"]}).status_code == 400

    draft = owner.post("/projects", data={"title": "Villa rewiring", "address": "Salwa", "bid_deadline": DEADLINE}).json()
    # Matching needs something to match against.
    assert owner.put(f"/projects/{draft['id']}/eligibility", json={"match_category": True}).status_code == 400
    r = owner.patch(f"/projects/{draft['id']}", json={"category_id": electrical["id"], "governorate": "hawalli"})
    assert r.json()["trade"] == "Electrical" and r.json()["category_id"] == electrical["id"]
    assert owner.put(f"/projects/{draft['id']}/eligibility", json={"match_category": True, "match_governorate": True}).status_code == 200
    pid = draft["id"]
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200

    noor, _ = _provider(db, "noor@example.com")
    assert noor.put("/service-provider/services", json={"categories": [electrical["id"]], "governorates": ["hawalli"]}).status_code == 200
    assert noor.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 200

    anywhere, _ = _provider(db, "kuwaitwide@example.com")  # no governorates declared = all of Kuwait
    anywhere.put("/service-provider/services", json={"categories": [electrical["id"]]})
    assert anywhere.get(f"/projects/{pid}/eligibility").json()["eligible"] is True

    sami, _ = _provider(db, "sami@example.com")
    assert sami.put("/service-provider/services", json={"categories": [plumbing["id"]], "governorates": ["mars"]}).status_code == 400
    sami.put("/service-provider/services", json={"categories": [plumbing["id"]], "governorates": ["ahmadi"]})
    assert all(p["id"] != pid for p in sami.get("/service-provider/feed").json()["items"])  # Stage 4.1: not in their feed
    assert [(r["code"], r["name"], r["governorate"]) for r in sami.get(f"/projects/{pid}/eligibility").json()["reasons"]] == [
        ("category_not_offered", "Electrical", None),
        ("governorate_not_served", None, "hawalli"),
    ]
    assert sami.post(f"/projects/{pid}/offers", json={"amount": "800"}).status_code == 403
    # Self-declared, so the provider can put it right at once.
    sami.put("/service-provider/services", json={"categories": [plumbing["id"], electrical["id"]], "governorates": ["ahmadi", "hawalli"]})
    assert sami.post(f"/projects/{pid}/offers", json={"amount": "800"}).status_code == 200

    # The rules were published on this category and governorate: they're fixed.
    assert owner.patch(f"/projects/{pid}", json={"category_id": plumbing["id"]}).status_code == 409
    assert owner.patch(f"/projects/{pid}", json={"governorate": "jahra"}).status_code == 409
    # A rename follows through to the requirement.
    admin.patch(f"/admin/categories/{electrical['id']}", json={"name": "Electrical works"})
    assert owner.get(f"/projects/{pid}").json()["trade"] == "Electrical works"


def test_verified_provider_adds_a_qualification_without_losing_access(db):
    licence = DocumentRequirement(name="Electrical works licence", is_required=False, applies_to=UserRole.service_provider, requires_expiry=True)
    baseline = DocumentRequirement(name="Commercial registration", is_required=True, applies_to=UserRole.service_provider)
    db.add_all([licence, baseline])
    db.commit()
    admin = _admin(db)
    sp, sp_id = _provider(db, "noor@example.com")

    # A required (baseline) document is still only changed through verification.
    assert sp.post(f"/service-provider/documents/{baseline.id}/upload", files={"file": ("cr.pdf", b"%PDF", "application/pdf")}).status_code == 409
    # An optional qualification can be added after approval...
    r = sp.post(f"/service-provider/documents/{licence.id}/upload", files={"file": ("lic.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    profile = sp.get("/service-provider/profile").json()
    assert profile["verification_status"] == "approved" and profile["marketplace_status"] == "verified_active"
    assert sp.get("/service-provider/feed").status_code == 200  # still in the marketplace
    # ...and reaches the admin's queue as a document to review.
    entry = next(e for e in admin.get("/admin/review/queue").json() if e["service_provider"]["user_id"] == sp_id)
    assert any(d["requirement_id"] == licence.id and d["status"] == "pending" for d in entry["documents"])

    # A correction to it doesn't reopen the whole verification.
    decision = {"service_provider_id": sp_id, "requirement_id": licence.id}
    assert admin.post("/admin/review/documents", json={**decision, "decision": "rejected", "note": "Page 2 missing"}).status_code == 200
    assert sp.get("/service-provider/profile").json()["verification_status"] == "approved"
    sp.post(f"/service-provider/documents/{licence.id}/upload", files={"file": ("lic.pdf", b"%PDF-2", "application/pdf")})
    expiry = (date.today() + timedelta(days=365)).isoformat()
    assert admin.post("/admin/review/documents", json={**decision, "decision": "approved", "expires_on": expiry}).status_code == 200

    owner = _owner(db)
    pid = owner.post("/projects", data={"title": "Fit-out", "address": "Salwa", "bid_deadline": DEADLINE}).json()["id"]
    owner.put(f"/projects/{pid}/eligibility", json={"qualifications": [licence.id]})
    owner.post(f"/owner/projects/{pid}/publish")
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "1200"}).status_code == 200


def test_admin_offer_edits_follow_the_same_rules(db):
    licence = DocumentRequirement(name="Electrical works licence", is_required=False, applies_to=UserRole.service_provider)
    db.add(licence)
    db.commit()
    admin = _admin(db)
    owner = _owner(db)
    sp, sp_id = _provider(db, "noor@example.com")
    doc = db.query(ServiceProviderDocument).filter_by(service_provider_id=sp_id, requirement_id=licence.id).first()
    if doc is None:
        doc = ServiceProviderDocument(service_provider_id=sp_id, requirement_id=licence.id)
        db.add(doc)
    doc.status = DocumentStatus.approved
    db.commit()

    pid = owner.post("/projects", data={"title": "Fit-out", "address": "Salwa", "bid_deadline": DEADLINE}).json()["id"]
    owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [{"description": "Cable", "quantity": "100", "unit": "m"}, {"description": "DB board", "quantity": None, "unit": None}]})
    owner.put(f"/projects/{pid}/eligibility", json={"qualifications": [licence.id]})
    owner.post(f"/owner/projects/{pid}/publish")
    items = owner.get(f"/projects/{pid}").json()["items"]
    offer = sp.post(f"/projects/{pid}/offers", json={"item_prices": [{"item_id": items[0]["id"], "rate": "1.500"}, {"item_id": items[1]["id"], "rate": "350"}]}).json()

    # Priced per item: the total can't be edited on its own...
    assert admin.patch(f"/admin/offers/{offer['id']}", json={"amount": "999"}).status_code == 400
    # ...a corrected rate recomputes it, and the earlier rates stay in the history.
    r = admin.patch(f"/admin/offers/{offer['id']}", json={"item_prices": [{"item_id": items[0]["id"], "rate": "1.250"}, {"item_id": items[1]["id"], "rate": "350"}]})
    assert r.status_code == 200 and Decimal(str(r.json()["amount"])) == Decimal("475.000")
    assert db.query(OfferRevision).one().item_prices[0]["rate"] == "1.500"

    # Once the provider is no longer eligible, an admin can't change the bid either.
    doc.expires_on = date.today() - timedelta(days=1)
    db.commit()
    r = admin.patch(f"/admin/offers/{offer['id']}", json={"message": "corrected"})
    assert r.status_code == 409 and "expired" in r.json()["detail"]

    # A one-total requirement takes an amount, not item rates.
    lump = owner.post("/projects", data={"title": "AC service", "address": "Salmiya", "bid_deadline": DEADLINE, "status": "open"}).json()["id"]
    lump_offer = sp.post(f"/projects/{lump}/offers", json={"amount": "185.750"}).json()
    assert admin.patch(f"/admin/offers/{lump_offer['id']}", json={"item_prices": []}).status_code == 400
    assert admin.patch(f"/admin/offers/{lump_offer['id']}", json={"amount": "180"}).status_code == 200
    assert db.get(Project, lump) is not None

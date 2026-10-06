"""Stage 3.8: the requirement says what providers must submit; the existing
offer system checks each response against it. Uses a realistic Kuwait
requirement priced per item in KWD."""
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.offer import Offer, OfferRevision
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat()
ITEMS = [
    {"description": "Excavation for footings", "quantity": "18.5", "unit": "m³"},
    {"description": "RC footings, C30", "quantity": "12", "unit": "m³"},
    {"description": "Site supervision", "quantity": None, "unit": None},
]
RULES = {
    "completion_period": "required",
    "approach": "required",
    "documents": [{"name": "Method statement", "required": True}, {"name": "Programme", "required": False}],
    "declarations": ["I have visited the site in Mishref.", "Prices include delivery to site and all labour."],
}


def _verified(db, role: str, email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.company_name = email.split("@")[0]
        profile.payment_override_active = True
    db.commit()
    return c


def _requirement(owner: TestClient, db, tender_type="owner_visible") -> dict:
    draft = owner.post("/projects", data={"title": "Majlis extension", "address": "Mishref", "bid_deadline": DEADLINE, "tender_type": tender_type}).json()
    assert owner.put(f"/projects/{draft['id']}/items", json={"pricing_basis": "per_item", "items": ITEMS}).status_code == 200
    r = owner.put(f"/projects/{draft['id']}/response-requirements", json=RULES)
    assert r.status_code == 200, r.text
    assert owner.post(f"/owner/projects/{draft['id']}/publish").status_code == 200
    return owner.get(f"/projects/{draft['id']}").json()


def test_provider_sees_what_to_submit_and_a_complete_response_is_accepted(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "alpha@example.com")
    req = _requirement(owner, db)
    pid = req["id"]

    # What the provider sees before responding.
    seen = sp.get(f"/projects/{pid}").json()
    assert seen["currency"] == "KWD" and seen["pricing_basis"] == "per_item"
    assert seen["response_requirements"] == RULES
    items = seen["items"]

    # An incomplete response is refused, naming everything missing.
    r = sp.post(f"/projects/{pid}/offers", json={"item_prices": [{"item_id": i["id"], "rate": "1"} for i in items]})
    assert r.status_code == 400
    for missing in ("completion period", "technical approach", "Method statement", "declaration"):
        assert missing in r.json()["detail"]
    # Every item must be priced, once.
    assert sp.post(f"/projects/{pid}/offers", json={"item_prices": [{"item_id": items[0]["id"], "rate": "1"}]}).status_code == 400
    # Only the documents the requirement asks for can be attached.
    assert sp.post(f"/projects/{pid}/offers/documents", data={"label": "CV"}, files={"file": ("cv.pdf", b"%PDF", "application/pdf")}).status_code == 400

    r = sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("method.pdf", b"%PDF-1", "application/pdf")})
    assert r.status_code == 200 and r.json()[0]["label"] == "Method statement"

    response = {
        "item_prices": [
            {"item_id": items[0]["id"], "rate": "4.250"},  # KWD per m³
            {"item_id": items[1]["id"], "rate": "62.500"},
            {"item_id": items[2]["id"], "rate": "750"},  # no quantity: a lump price for the item
        ],
        "timeline_estimate": "10 weeks from site handover",
        "message": "Excavate with mini-excavator; ready-mix C30 from a Shuwaikh plant.",
        "assumptions": "Excludes dewatering if groundwater is met.",
        "accepted_declarations": RULES["declarations"],
    }
    r = sp.post(f"/projects/{pid}/offers", json=response)
    assert r.status_code == 200, r.text
    offer = r.json()
    # 18.5 x 4.250 + 12 x 62.500 + 750 = 78.625 + 750 + 750
    assert Decimal(str(offer["amount"])) == Decimal("1578.625")
    assert [Decimal(line["line_total"]) for line in offer["item_prices"]] == [Decimal("78.625"), Decimal("750.000"), Decimal("750.000")]
    assert offer["declarations_accepted"] == RULES["declarations"] and offer["documents"][0]["url"]

    # The owner gets a structured, comparable response.
    owner_view = owner.get(f"/owner/projects/{pid}/offers").json()[0]
    assert owner_view["assumptions"].startswith("Excludes dewatering")
    assert owner_view["documents"][0]["file_name"] == "method.pdf" and owner_view["item_prices"][1]["rate"] == "62.500"

    # Revising keeps the earlier prices in the offer's history.
    response["item_prices"][2]["rate"] = "600"
    assert sp.post(f"/projects/{pid}/offers", json=response).status_code == 200
    revision = db.query(OfferRevision).one()
    assert revision.item_prices[2]["rate"] == "750" and Decimal(str(revision.amount)) == Decimal("1578.625")
    assert db.query(Offer).count() == 1  # still one offer per provider


def test_rules_are_draft_only_and_simple_requirements_still_need_only_a_price(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "alpha@example.com")
    published = _requirement(owner, db)
    assert owner.put(f"/projects/{published['id']}/response-requirements", json={}).status_code == 409
    assert owner.put(
        f"/projects/{published['id']}/response-requirements", json={"documents": [{"name": "A"}, {"name": "a"}]}
    ).status_code in (409, 422)

    simple = owner.post("/projects", data={"title": "AC service", "address": "Salmiya", "bid_deadline": DEADLINE, "status": "open"}).json()
    seen = sp.get(f"/projects/{simple['id']}").json()
    assert seen["pricing_basis"] == "lump_sum" and seen["response_requirements"]["documents"] == []
    r = sp.post(f"/projects/{simple['id']}/offers", json={"amount": "185.750"})
    assert r.status_code == 200 and Decimal(str(r.json()["amount"])) == Decimal("185.750")
    assert sp.post(f"/projects/{simple['id']}/offers", json={"amount": "1.2345"}).status_code == 422  # more than 3 decimals


def test_sealed_responses_and_attachments_stay_private(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    beta = _verified(db, "service_provider", "beta@example.com")
    req = _requirement(owner, db, tender_type="sealed")
    pid, items = req["id"], req["items"]
    alpha.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("m.pdf", b"%PDF", "application/pdf")})
    doc_id = alpha.get(f"/projects/{pid}/offers/documents").json()[0]["id"]
    alpha.post(
        f"/projects/{pid}/offers",
        json={
            "item_prices": [{"item_id": i["id"], "rate": "10"} for i in items],
            "timeline_estimate": "8 weeks",
            "message": "Method",
            "assumptions": "None",
            "accepted_declarations": RULES["declarations"],
        },
    )

    # Sealed and open: the owner sees that a bid exists, nothing of its content.
    sealed_view = owner.get(f"/owner/projects/{pid}/offers").json()[0]
    assert sealed_view["sealed"] is True
    assert sealed_view["item_prices"] is None and sealed_view["assumptions"] is None and sealed_view["documents"] == []

    # Another provider can neither list nor remove alpha's attachments.
    assert beta.get(f"/projects/{pid}/offers/documents").json() == []
    assert beta.delete(f"/projects/{pid}/offers/documents/{doc_id}").status_code == 404

    # After the deadline, attachments can't be changed.
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert alpha.delete(f"/projects/{pid}/offers/documents/{doc_id}").status_code == 400

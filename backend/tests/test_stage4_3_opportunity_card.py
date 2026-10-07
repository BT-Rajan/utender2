"""Stage 4.3: each feed item answers what, where, how it's priced, when to
respond and when the work is expected, who may respond -- from the same
record the requirement page shows, without becoming that page."""
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.category import ServiceCategory
from app.models.enums import StakeholderType, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile

SCOPE = "Supply and install LED lighting in a 400 m² shop in Salmiya, including the DB board upgrade. " * 4


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _verified(db, role: str, email: str, organization=False) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.company_name = email.split("@")[0]
        profile.payment_override_active = True
        if organization:
            profile.stakeholder_type = StakeholderType.organization
    db.commit()
    return c


def test_a_card_is_a_decision_summary_of_the_real_requirement(db):
    electrical = ServiceCategory(name="Electrical", is_active=True)
    db.add(electrical)
    db.commit()
    owner = _verified(db, "owner", "owner@example.com")
    company = _verified(db, "service_provider", "noor@example.com", organization=True)
    start = (date.today() + timedelta(days=30)).isoformat()
    deadline = _when(9)
    pid = owner.post(
        "/projects",
        data={"title": "Shop lighting", "address": "Salmiya, block 10, shop 4", "governorate": "hawalli", "area": "Salmiya", "category_id": electrical.id, "description": SCOPE, "bid_deadline": deadline, "expected_start_date": start, "expected_duration_days": "14", "tender_type": "sealed"},
        files=[("drawings", ("layout.pdf", b"%PDF", "application/pdf")), ("drawings", ("boq.xlsx", b"PK", "application/vnd.ms-excel"))],
    ).json()["id"]
    owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [{"description": "LED panel", "quantity": "60", "unit": "no."}, {"description": "DB board", "quantity": "1", "unit": "no."}]})
    owner.put(f"/projects/{pid}/eligibility", json={"provider_type": "organization"})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200

    page = company.get("/service-provider/feed", params={"search": "lighting", "governorate": "hawalli", "sort": "newest"}).json()
    card = page["items"][0]
    # What, where, how it's priced, how much there is to it.
    assert (card["id"], card["title"], card["trade"], card["governorate"], card["area"]) == (pid, "Shop lighting", "Electrical", "hawalli", "Salmiya")
    assert (card["pricing_basis"], card["item_count"], card["document_count"], card["tender_type"]) == ("per_item", 2, 2, "sealed")
    assert card["summary"].startswith("Supply and install LED lighting") and len(card["summary"]) < len(SCOPE)
    # When: respond by, and when the work is expected; published when.
    assert card["bid_deadline"] == deadline and card["expected_start_date"] == start and card["expected_duration_days"] == 14 and card["published_at"]
    # Who may respond -- and that this provider does.
    assert card["conditions"]["provider_type"] == "organization" and card["eligible"] is True
    # Not the requirement page: no address, no full scope, documents or items.
    assert card["address"] is None and card["description"] is None and "drawings" not in card and "items" not in card
    # Opening it reaches the same requirement, with the same facts.
    detail = company.get(f"/projects/{pid}").json()
    assert (detail["id"], detail["title"], detail["bid_deadline"], detail["tender_type"]) == (pid, card["title"], card["bid_deadline"], card["tender_type"])
    assert detail["address"] == "Salmiya, block 10, shop 4" and detail["description"] == SCOPE


def test_an_unrestricted_card_says_nothing_about_conditions(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sami@example.com")
    owner.post("/projects", data={"title": "Fence painting", "address": "x", "description": "Paint a 60 m fence.", "bid_deadline": _when(5), "status": "open"})
    card = sp.get("/service-provider/feed").json()["items"][0]
    assert card["conditions"] is None and card["document_count"] == 0 and card["pricing_basis"] == "lump_sum"

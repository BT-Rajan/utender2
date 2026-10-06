"""Stage 3.5: site and location. A draft carries its governorate and area
(enough for a provider to judge relevance and travel) plus the exact address,
which is disclosed only where a provider can open the full requirement --
never in the listing a merely verified provider can browse."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat()
SITE = {
    "governorate": "mubarak_al_kabeer",
    "area": "Mishref",
    "address": "Block 4, Street 12, House 7 (corner plot, entrance from Street 12)",
}


def _verified(db, role: str, email: str, active: bool = True) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.payment_override_active = active
    db.commit()
    return c


def test_owner_saves_site_location_and_finds_it_again(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = owner.post("/projects", data={"title": "Majlis extension", "address": "Mishref", "bid_deadline": DEADLINE}).json()
    assert owner.patch(f"/projects/{draft['id']}", json=SITE).status_code == 200

    again = TestClient(app)
    again.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    saved = again.get(f"/projects/{draft['id']}").json()
    assert {k: saved[k] for k in SITE} == SITE and saved["status"] == "draft"

    # Editable, including clearing the area; governorate must be a real one.
    assert again.patch(f"/projects/{draft['id']}", json={"area": "", "governorate": "hawalli"}).json()["area"] is None
    assert again.patch(f"/projects/{draft['id']}", json={"governorate": "Atlantis"}).status_code == 400

    # The creation form can set it up front too.
    r = owner.post("/projects", data={"title": "AC service", "bid_deadline": DEADLINE, **SITE})
    assert {k: r.json()[k] for k in SITE} == SITE


def test_listing_shows_area_not_exact_address(db):
    owner = _verified(db, "owner", "owner@example.com")
    published = owner.post("/projects", data={"title": "Majlis extension", "bid_deadline": DEADLINE, "status": "open", "description": "Site: narrow street access.", **SITE}).json()
    owner.post("/projects", data={"title": "Shop fit-out", "address": "Fahaheel", "governorate": "ahmadi", "area": "Fahaheel", "bid_deadline": DEADLINE, "status": "open"})

    browsing = _verified(db, "service_provider", "browsing@example.com", active=False)  # verified, no active access
    listing = browsing.get("/service-provider/feed").json()
    card = next(p for p in listing if p["id"] == published["id"])
    assert (card["governorate"], card["area"]) == ("mubarak_al_kabeer", "Mishref")
    assert card["address"] is None and card["description"] is None  # exact address and site notes withheld

    # Filter by governorate to see what's in my service area; search never probes the address.
    assert [p["title"] for p in browsing.get("/service-provider/feed", params={"governorate": "ahmadi"}).json()] == ["Shop fit-out"]
    assert browsing.get("/service-provider/feed", params={"search": "House 7"}).json() == []
    assert len(browsing.get("/service-provider/feed", params={"search": "Mishref"}).json()) == 1  # area is searchable
    assert browsing.get(f"/projects/{published['id']}").status_code == 404  # full requirement needs active access

    # A provider with active access opens the full requirement, exact address included.
    active = _verified(db, "service_provider", "active@example.com")
    assert active.get(f"/projects/{published['id']}").json()["address"] == SITE["address"]


def test_draft_location_stays_private(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = owner.post("/projects", data={"title": "Majlis extension", "bid_deadline": DEADLINE, **SITE}).json()
    sp = _verified(db, "service_provider", "sp@example.com")
    assert sp.get(f"/projects/{draft['id']}").status_code == 404
    assert draft["id"] not in [p["id"] for p in sp.get("/service-provider/feed").json()]
    other = _verified(db, "owner", "other@example.com")
    assert other.patch(f"/projects/{draft['id']}", json={"area": "x"}).status_code == 404

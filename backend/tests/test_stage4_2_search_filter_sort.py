"""Stage 4.2: a provider narrows the opportunities available to them -- by
text, type of work, governorate, their own declared services and areas, time
left to respond -- and orders them, all in the database query, page by page,
never past what they may discover."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.category import ServiceCategory
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _verified(db, role: str, email: str, paid: bool = True) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.company_name = email.split("@")[0]
        profile.payment_override_active = paid
    db.commit()
    return c


def _publish(owner, title, category, governorate, days, description="Work as described.", **extra):
    r = owner.post("/projects", data={"title": title, "address": "Plot 1", "governorate": governorate, "category_id": category, "description": description, "bid_deadline": _when(days), "status": "open", **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _titles(client, **params):
    r = client.get("/service-provider/feed", params=params)
    assert r.status_code == 200, r.text
    return [p["title"] for p in r.json()["items"]]


def _market(db):
    electrical, painting = ServiceCategory(name="Electrical", is_active=True), ServiceCategory(name="Painting", is_active=True)
    db.add_all([electrical, painting])
    db.commit()
    owner = _verified(db, "owner", "owner@example.com")
    _publish(owner, "Villa rewiring", electrical.id, "capital", 2, "Rewire a villa in Kaifan: new DB board, 40 points.")
    _publish(owner, "Shop lighting", electrical.id, "hawalli", 12, "LED lighting for a Salmiya shop.")
    _publish(owner, "Warehouse power", electrical.id, "ahmadi", 20, "Three-phase supply to a warehouse.")
    _publish(owner, "Apartment painting", painting.id, "capital", 8, "Paint a 3-bedroom apartment, emulsion.")
    _publish(owner, "Fence painting", painting.id, "jahra", 30, "Paint a 60 m fence.")
    restricted = owner.post("/projects", data={"title": "Electrical substation", "address": "x", "governorate": "capital", "category_id": electrical.id, "bid_deadline": _when(9)}).json()["id"]
    owner.put(f"/projects/{restricted}/eligibility", json={"provider_type": "organization"})
    owner.post(f"/owner/projects/{restricted}/publish")
    owner.post("/projects", data={"title": "Electrical draft", "address": "x", "governorate": "capital", "category_id": electrical.id, "bid_deadline": _when(9)})
    # Publication times a minute apart, in the order above (the same second otherwise).
    order = ["Villa rewiring", "Shop lighting", "Warehouse power", "Apartment painting", "Fence painting"]
    for p in db.query(Project).filter(Project.title.in_(order)):
        p.published_at = datetime.utcnow() - timedelta(minutes=10 - order.index(p.title))
    db.commit()
    return owner, electrical, painting


def test_search_filter_sort_and_combine(db):
    owner, electrical, painting = _market(db)
    sp = _verified(db, "service_provider", "sami@example.com")

    # Default: everything available, closing soonest -- not the restricted one, nor the draft.
    assert _titles(sp) == ["Villa rewiring", "Apartment painting", "Shop lighting", "Warehouse power", "Fence painting"]
    # 1. Text: every word, across title, area, type of work and (for a provider who can read it) the scope.
    assert _titles(sp, search="painting") == ["Apartment painting", "Fence painting"]
    assert _titles(sp, search="electrical") == ["Villa rewiring", "Shop lighting", "Warehouse power"]  # type of work
    assert _titles(sp, search="DB board") == ["Villa rewiring"]  # scope
    assert _titles(sp, search="paint fence") == ["Fence painting"]  # all words
    assert _titles(sp, search="substation") == []  # restricted: never found
    assert _titles(sp, search="Plot") == []  # the exact address is never searched
    assert _titles(sp, search="100%") == []  # typed wildcards are literal
    # 2. Type of work; 3. governorate.
    assert _titles(sp, category_id=painting.id) == ["Apartment painting", "Fence painting"]
    assert _titles(sp, governorate="capital") == ["Villa rewiring", "Apartment painting"]
    # 4. Time left to respond.
    assert _titles(sp, min_days=10) == ["Shop lighting", "Warehouse power", "Fence painting"]
    # 5. Sorting.
    assert _titles(sp, sort="deadline_latest") == ["Fence painting", "Warehouse power", "Shop lighting", "Apartment painting", "Villa rewiring"]
    assert _titles(sp, sort="newest") == ["Fence painting", "Apartment painting", "Warehouse power", "Shop lighting", "Villa rewiring"]
    assert sp.get("/service-provider/feed", params={"sort": "best"}).status_code == 422
    # 6. Together: open electrical work, in my area, with time to respond.
    assert _titles(sp, category_id=electrical.id, governorate="hawalli", min_days=5, sort="newest") == ["Shop lighting"]
    assert _titles(sp, search="paint", governorate="capital", sort="deadline_latest") == ["Apartment painting"]
    # 8. Clearing returns the normal feed.
    assert _titles(sp) == _titles(sp, search="", governorate="", sort="deadline")


def test_my_services_and_areas(db):
    owner, electrical, painting = _market(db)
    sp = _verified(db, "service_provider", "sami@example.com")
    assert _titles(sp, my_services=True) == []  # nothing declared yet: no types of work of mine
    sp.put("/service-provider/services", json={"categories": [electrical.id], "governorates": ["capital", "hawalli"]})
    assert _titles(sp, my_services=True) == ["Villa rewiring", "Shop lighting", "Warehouse power"]
    assert _titles(sp, my_areas=True) == ["Villa rewiring", "Apartment painting", "Shop lighting"]
    assert _titles(sp, my_services=True, my_areas=True, min_days=5) == ["Shop lighting"]
    sp.put("/service-provider/services", json={"categories": [electrical.id], "governorates": []})  # all of Kuwait
    assert len(_titles(sp, my_areas=True)) == 5


def test_paused_and_paging_keep_the_query(db):
    owner, electrical, painting = _market(db)
    sp = _verified(db, "service_provider", "sami@example.com")
    paused = next(p for p in owner.get("/owner/projects").json() if p["title"] == "Shop lighting")["id"]
    owner.post(f"/owner/projects/{paused}/pause", json={"reason": "Waiting for the landlord."})
    assert "Shop lighting" in _titles(sp) and "Shop lighting" not in _titles(sp, accepting=True)
    # 7. Pages of a filtered, sorted query: the same query, in order, without overlap.
    params = {"category_id": electrical.id, "sort": "deadline_latest", "limit": 2}
    first = sp.get("/service-provider/feed", params=params).json()
    second = sp.get("/service-provider/feed", params={**params, "offset": first["next_offset"]}).json()
    assert [p["title"] for p in first["items"] + second["items"]] == ["Warehouse power", "Shop lighting", "Villa rewiring"]
    assert second["next_offset"] is None


def test_narrowing_never_widens_or_leaks(db):
    owner, electrical, painting = _market(db)
    unpaid = _verified(db, "service_provider", "free@example.com", paid=False)
    sp = _verified(db, "service_provider", "sami@example.com")
    # The scope isn't searchable for a provider who can't read it.
    assert _titles(unpaid, search="DB board") == [] and _titles(unpaid, search="rewiring") == ["Villa rewiring"]
    # 9. Nothing matches: a plain empty page -- no count of restricted requirements that would have.
    r = sp.get("/service-provider/feed", params={"search": "substation"}).json()
    assert r == {"items": [], "next_offset": None, "hidden_ineligible": None}
    # 10. No parameter reaches past the lifecycle or eligibility rules.
    for gone in ("Electrical substation", "Electrical draft"):
        for params in ({"search": gone}, {"category_id": electrical.id}, {"governorate": "capital", "sort": "newest"}, {"min_days": 0, "accepting": False}):
            assert gone not in _titles(sp, **params)
    ended = next(p for p in owner.get("/owner/projects").json() if p["title"] == "Fence painting")["id"]
    owner.post(f"/owner/projects/{ended}/cancel", json={"reason": "not_needed"})
    db.get(Project, next(p["id"] for p in owner.get("/owner/projects").json() if p["title"] == "Villa rewiring")).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert _titles(sp, search="painting") == ["Apartment painting"] and "Villa rewiring" not in _titles(sp, search="rewiring")
    assert sp.get("/service-provider/feed", params={"limit": 1000}).status_code == 422

"""Stage 4.1: a provider's feed holds the published opportunities they can
actually take part in -- and nothing that isn't currently available -- a page
at a time, each item enough to decide whether to open it."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.enums import UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User

SCOPE = "Supply and install 14 split AC units (2.5 t) across two floors, including copper piping, drainage and commissioning. Site access via the side gate; parking on the street only. " * 2


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _verified(db, role: str, email: str, organization: bool = False, paid: bool = True) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "organization", "legal_name": email.split("@")[0] + " W.L.L.", "authorized": True} if organization else {"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.company_name = email.split("@")[0]
        profile.payment_override_active = paid
    db.commit()
    return c


def _publish(owner, title, days=10, **extra) -> str:
    r = owner.post("/projects", data={"title": title, "address": "Jabriya, block 9, house 4", "governorate": "hawalli", "area": "Jabriya", "description": SCOPE, "bid_deadline": _when(days), "status": "open", **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _feed(client, **params):
    r = client.get("/service-provider/feed", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _ids(client, **params):
    return [p["id"] for p in _feed(client, **params)["items"]]


def test_the_feed_holds_only_what_is_available_to_this_provider(db):
    owner = _verified(db, "owner", "owner@example.com")
    individual = _verified(db, "service_provider", "sami@example.com")
    company = _verified(db, "service_provider", "noor@example.com", organization=True)
    admin_user = User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="A")
    db.add(admin_user)
    db.commit()
    admin = TestClient(app)
    admin.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})

    open_pid = _publish(owner, "AC installation")
    draft = owner.post("/projects", data={"title": "Draft job", "address": "x", "bid_deadline": _when(10)}).json()["id"]
    org_only = owner.post("/projects", data={"title": "Organizations only", "address": "Salmiya", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{org_only}/eligibility", json={"provider_type": "organization"})
    owner.post(f"/owner/projects/{org_only}/publish")
    suspended, canceled, passed, closed = (_publish(owner, t) for t in ("Suspended", "Canceled", "Passed", "Closed"))
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})
    owner.post(f"/owner/projects/{canceled}/cancel", json={"reason": "not_needed"})
    company.post(f"/projects/{closed}/offers", json={"amount": "100"})
    owner.post(f"/owner/projects/{closed}/close")
    db.get(Project, passed).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    # 1/4. Open and eligible: there. 2. Not eligible: not offered. 3/5/6/7. Not available: never.
    assert _ids(individual) == [open_pid]
    assert set(_ids(company)) == {open_pid, org_only}
    for gone in (draft, suspended, canceled, passed, closed):
        assert gone not in _ids(company) + _ids(individual)

    # 8/9. Asking directly still goes through the same rules.
    for pid in (draft, suspended, canceled, passed, org_only):
        assert individual.get(f"/projects/{pid}").status_code == 404, pid
        assert individual.post(f"/projects/{pid}/offers", json={"amount": "50"}).status_code in (400, 403, 404), pid

    # 10. Published later: discoverable at once.
    fresh = _publish(owner, "Water heater swap", days=3)
    assert _ids(individual)[0] == fresh  # closing soonest first


def test_each_item_is_a_summary_not_the_requirement(db):
    owner = _verified(db, "owner", "owner@example.com")
    paid = _verified(db, "service_provider", "paid@example.com")
    unpaid = _verified(db, "service_provider", "unpaid@example.com", paid=False)
    pid = _publish(owner, "AC installation")
    item = _feed(paid)["items"][0]
    assert (item["title"], item["governorate"], item["area"], item["pricing_basis"], item["item_count"]) == ("AC installation", "hawalli", "Jabriya", "lump_sum", 0)
    assert item["bid_deadline"] and item["published_at"] and item["eligible"] is True
    assert item["address"] is None and item["description"] is None  # the full requirement stays on its page
    assert item["summary"].startswith("Supply and install 14 split AC units") and item["summary"].endswith("…") and len(item["summary"]) <= 241
    # Without full access, the listing level only.
    assert _feed(unpaid)["items"][0]["summary"] is None


def test_pages_are_bounded_stable_and_complete(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sami@example.com")
    pids = [_publish(owner, f"Job {i:02}", days=5 + i) for i in range(7)]
    first = _feed(sp, limit=3)
    assert [p["id"] for p in first["items"]] == pids[:3] and first["next_offset"] == 3
    second = _feed(sp, limit=3, offset=3)
    third = _feed(sp, limit=3, offset=second["next_offset"])
    assert [p["id"] for p in second["items"] + third["items"]] == pids[3:] and third["next_offset"] is None
    assert sp.get("/service-provider/feed", params={"limit": 500}).status_code == 422  # never everything at once
    assert len(_feed(sp)["items"]) == 7  # default page holds them


def test_an_empty_feed_says_whether_anything_was_left_out(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sami@example.com")
    assert _feed(sp) == {"items": [], "next_offset": None, "hidden_ineligible": 0}
    pid = owner.post("/projects", data={"title": "Organizations only", "address": "Salmiya", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{pid}/eligibility", json={"provider_type": "organization"})
    owner.post(f"/owner/projects/{pid}/publish")
    assert _feed(sp) == {"items": [], "next_offset": None, "hidden_ineligible": 1}


def test_a_bid_stays_in_view_after_a_qualification_lapses(db):
    from app.models.document import DocumentRequirement, ServiceProviderDocument
    from app.models.enums import DocumentStatus

    licence = DocumentRequirement(name="Electrical works licence", is_required=False, applies_to=UserRole.service_provider)
    db.add(licence)
    db.commit()
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "noor@example.com")
    sp_id = sp.get("/auth/me").json()["id"]
    doc = db.query(ServiceProviderDocument).filter_by(service_provider_id=sp_id, requirement_id=licence.id).first() or ServiceProviderDocument(service_provider_id=sp_id, requirement_id=licence.id)
    doc.status = DocumentStatus.approved
    db.add(doc)
    db.commit()
    pid = owner.post("/projects", data={"title": "Rewiring", "address": "Salwa", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{pid}/eligibility", json={"qualifications": [licence.id]})
    owner.post(f"/owner/projects/{pid}/publish")
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 200
    doc.status = DocumentStatus.rejected
    db.commit()
    item = next(p for p in _feed(sp)["items"] if p["id"] == pid)
    assert item["my_offer_status"] == "submitted" and item["eligible"] is False  # theirs, with why it can't be revised

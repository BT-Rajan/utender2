"""Stage 3.4: the measurable pricing basis of a draft requirement -- items,
quantities, units and specifications, and whether providers price the whole
requirement or each item. Items are optional: a requirement that isn't
naturally itemized needs none."""
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import ProjectItem
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat()

ITEMS = [
    {"description": "Excavation for footings", "quantity": "18.5", "unit": "m³", "specification": "Depth 1.5 m below NGL; dispose off site."},
    {"description": "Reinforced concrete footings", "quantity": "12", "unit": "m³", "specification": "C30, sulphate-resisting cement."},
    {"description": "Porcelain floor tiles, supply and fix", "quantity": "40", "unit": "m²", "specification": "60×60 cm, owner to approve sample."},
    {"description": "Site supervision", "quantity": None, "unit": None, "specification": "Full-time engineer during structural works."},
]


def _verified(db, role: str, email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.payment_override_active = True
    db.commit()
    return c


def _draft(owner: TestClient, **extra) -> dict:
    return owner.post("/projects", data={"title": "Majlis extension", "address": "Mishref", "bid_deadline": DEADLINE, **extra}).json()


def _norm(items):
    return [
        {**i, "quantity": None if i["quantity"] is None else Decimal(str(i["quantity"]))}
        for i in ({k: x[k] for k in ("description", "quantity", "unit", "specification")} for x in items)
    ]


def test_items_and_pricing_basis_are_saved_reopened_and_edited(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = _draft(owner)
    assert draft["pricing_basis"] == "lump_sum" and draft["items"] == []  # default: one total, no items

    r = owner.put(f"/projects/{draft['id']}/items", json={"pricing_basis": "per_item", "items": ITEMS})
    assert r.status_code == 200, r.text

    again = TestClient(app)
    again.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    saved = again.get(f"/projects/{draft['id']}").json()
    assert saved["pricing_basis"] == "per_item"
    assert _norm(saved["items"]) == _norm(ITEMS)
    assert [i["position"] for i in saved["items"]] == [1, 2, 3, 4]
    assert saved["status"] == "draft"

    # Edit: drop one item, change a quantity -- the list is replaced as a whole.
    edited = [ITEMS[0] | {"quantity": "20"}, ITEMS[2]]
    r = again.put(f"/projects/{draft['id']}/items", json={"pricing_basis": "per_item", "items": edited})
    assert _norm(r.json()["items"]) == _norm(edited)
    assert db.query(ProjectItem).count() == 2


def test_a_non_itemized_requirement_needs_no_items(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = _draft(owner)
    r = owner.put(f"/projects/{draft['id']}/items", json={"pricing_basis": "lump_sum", "items": []})
    assert r.status_code == 200 and r.json()["items"] == []

    # Pricing per item without any item to price makes no sense.
    r = owner.put(f"/projects/{draft['id']}/items", json={"pricing_basis": "per_item", "items": []})
    assert r.status_code == 400

    # Blank descriptions and negative quantities are refused.
    assert owner.put(f"/projects/{draft['id']}/items", json={"pricing_basis": "lump_sum", "items": [{"description": " "}]}).status_code == 400
    assert owner.put(f"/projects/{draft['id']}/items", json={"pricing_basis": "lump_sum", "items": [{"description": "x", "quantity": "-1"}]}).status_code == 422


def test_items_respect_ownership_draft_state_and_reach_providers(db):
    owner = _verified(db, "owner", "owner@example.com")
    other = _verified(db, "owner", "other@example.com")
    sp = _verified(db, "service_provider", "sp@example.com")

    draft = _draft(owner)
    owner.put(f"/projects/{draft['id']}/items", json={"pricing_basis": "per_item", "items": ITEMS})
    assert other.put(f"/projects/{draft['id']}/items", json={"pricing_basis": "lump_sum", "items": []}).status_code == 404
    assert sp.get(f"/projects/{draft['id']}").status_code == 404  # private while a draft

    # Once published, a provider sees exactly what to price; the owner can no
    # longer swap the basis out from under them through this endpoint.
    published = _draft(owner, status="open")
    assert owner.put(f"/projects/{published['id']}/items", json={"pricing_basis": "lump_sum", "items": []}).status_code == 409
    db.add(ProjectItem(project_id=published["id"], position=1, description="Lump-sum item", quantity=Decimal("1"), unit="lot"))
    db.commit()
    seen = sp.get(f"/projects/{published['id']}").json()
    assert seen["pricing_basis"] == "lump_sum" and seen["items"][0]["description"] == "Lump-sum item"

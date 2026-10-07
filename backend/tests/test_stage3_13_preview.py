"""Stage 3.13: the owner's provider preview is built from the very record an
eligible provider receives once the requirement is published -- so what the
owner checks is what the provider gets -- and previewing neither publishes
nor exposes the draft."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat() + "Z"
# Fields that describe the requirement's state rather than its content: they
# legitimately change when it is published (or as offers arrive).
STATE = {"status", "published_at", "version", "updated_at", "offer_count", "tender_type_locked", "my_offer_status", "eligible", "ineligible_reasons"}


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


def _content(detail: dict) -> dict:
    content = {k: v for k, v in detail.items() if k not in STATE}
    content["tender_rules"] = {k: v for k, v in detail["tender_rules"].items() if k != "questions_open"}
    content["drawings"] = [{k: v for k, v in d.items() if k != "url"} for d in detail["drawings"]]  # signed links differ per request
    return content


def test_preview_is_what_the_provider_receives(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "fence@example.com")
    draft = owner.post(
        "/projects",
        data={
            "title": "Boundary wall — plot 12",
            "address": "Sabah Al-Ahmad, block 3, plot 12",
            "governorate": "ahmadi",
            "area": "Sabah Al-Ahmad",
            "trade": "Masonry",
            "description": "Build a 2.4 m block boundary wall (60 m) with RC columns every 3 m and one sliding gate.",
            "bid_deadline": DEADLINE,
        },
        files=[("drawings", ("wall-plan.pdf", b"%PDF-1", "application/pdf"))],
    ).json()
    pid = draft["id"]
    owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [{"description": "Blockwork", "quantity": "144", "unit": "m²"}]})
    owner.put(f"/projects/{pid}/response-requirements", json={"completion_period": "required", "declarations": ["I have visited the site."]})
    owner.put(f"/projects/{pid}/tender-rules", json={"commercial_conditions": {"offer_validity_days": 60}})

    # The preview: the owner's read of the draft. Providers still can't see it.
    preview = owner.get(f"/projects/{pid}").json()
    assert preview["status"] == "draft"
    assert sp.get(f"/projects/{pid}").status_code == 404
    assert all(p["id"] != pid for p in sp.get("/service-provider/feed").json())
    assert sp.get(f"/projects/{pid}/drawings-zip").status_code == 404
    # Previewing changes nothing.
    assert owner.get(f"/projects/{pid}").json()["version"] == preview["version"]

    # The owner corrects something after previewing, previews again...
    r = owner.patch(f"/projects/{pid}", json={"area": "Sabah Al-Ahmad Sea City"}, headers={"If-Match": str(preview["version"])})
    assert r.status_code == 200
    preview = owner.get(f"/projects/{pid}").json()
    assert preview["area"] == "Sabah Al-Ahmad Sea City"

    # ...and once published, an eligible provider receives exactly that content.
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    received = sp.get(f"/projects/{pid}").json()
    assert _content(received) == _content(preview)
    # The listing card shows the same, less: no exact address and no scope.
    card = next(p for p in sp.get("/service-provider/feed").json() if p["id"] == pid)
    assert card["address"] is None and card["description"] is None
    assert (card["title"], card["area"], card["trade"]) == (preview["title"], preview["area"], preview["trade"])


def test_only_the_owner_side_can_preview(db):
    owner = _verified(db, "owner", "owner@example.com")
    other_owner = _verified(db, "owner", "other@example.com")
    pid = owner.post("/projects", data={"title": "Private draft", "address": "Exact plot 7", "bid_deadline": DEADLINE}).json()["id"]
    assert other_owner.get(f"/projects/{pid}").status_code == 404
    assert TestClient(app).get(f"/projects/{pid}").status_code in (401, 403)
    assert owner.get(f"/projects/{pid}").json()["status"] == "draft"  # still a draft


def test_preview_shows_who_the_rules_reach(db):
    from app.models.document import DocumentRequirement, ServiceProviderDocument
    from app.models.enums import DocumentStatus, UserRole

    licence = DocumentRequirement(name="Electrical works licence", is_required=False, applies_to=UserRole.service_provider)
    db.add(licence)
    db.commit()
    owner = _verified(db, "owner", "owner@example.com")
    holder = _verified(db, "service_provider", "holder@example.com")
    _verified(db, "service_provider", "other@example.com")
    holder_id = holder.get("/auth/me").json()["id"]
    doc = db.query(ServiceProviderDocument).filter_by(service_provider_id=holder_id, requirement_id=licence.id).first() or ServiceProviderDocument(
        service_provider_id=holder_id, requirement_id=licence.id
    )
    doc.status = DocumentStatus.approved
    db.add(doc)
    db.commit()
    pid = owner.post("/projects", data={"title": "Rewiring", "address": "Salwa", "bid_deadline": DEADLINE}).json()["id"]
    assert owner.get(f"/projects/{pid}/audience").json() == {"active_providers": 2, "eligible": 2, "excluded_by": {}}
    owner.put(f"/projects/{pid}/eligibility", json={"provider_type": "organization", "qualifications": [licence.id]})
    reach = owner.get(f"/projects/{pid}/audience").json()
    # Counts only -- and a rule that shuts everyone out is visible before publishing.
    assert reach == {"active_providers": 2, "eligible": 0, "excluded_by": {"organization_only": 2, "qualification_missing": 1}}
    assert TestClient(app).get(f"/projects/{pid}/audience").status_code in (401, 403)
    assert holder.get(f"/projects/{pid}/audience").status_code == 404

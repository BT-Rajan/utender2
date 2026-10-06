"""Stage 3.3: the owner defines the scope of work on a draft (stored in the
existing Project.description field), saves it, and finds it unchanged --
structure and line breaks included -- when they come back."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile
from app.routers.projects import MAX_SCOPE_CHARS

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat()

SCOPE = """Overview:
Add a 40 m² majlis to an existing two-storey villa.

Work / tasks required:
- Excavation and foundations (isolated footings)
- RC frame, block walls, roof slab with waterproofing
- Finishes: porcelain flooring, gypsum ceiling, paint

Specifications & standards:
- Concrete C30, Kuwait Municipality building code
- Thermal insulation to MEW requirements

Quantities / measurements:
- Floor area: approx. 40 m², ceiling height 3.2 m

Included:
- All materials, labour and site cleaning

Excluded (by owner or others):
- Furniture and curtains

Site & working conditions:
- Occupied villa; work hours 7 am–5 pm, no Friday work

ملاحظة: يجب الحصول على موافقة البلدية قبل البدء."""


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
    data = {"title": "Villa extension", "address": "Mishref, Block 4", "bid_deadline": DEADLINE, **extra}
    return owner.post("/projects", data=data).json()


def test_scope_is_saved_and_reopened_exactly(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = _draft(owner)
    assert owner.patch(f"/projects/{draft['id']}", json={"description": SCOPE}).status_code == 200

    again = TestClient(app)
    again.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    saved = again.get(f"/projects/{draft['id']}").json()
    assert saved["description"] == SCOPE  # line breaks, lists and Arabic preserved
    assert saved["status"] == "draft"

    # ...and can be edited again.
    edited = SCOPE.replace("approx. 40 m²", "approx. 45 m²")
    assert again.patch(f"/projects/{draft['id']}", json={"description": edited}).json()["description"] == edited


def test_scope_length_limit_is_a_clear_error(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = _draft(owner)
    too_long = "ب" * (MAX_SCOPE_CHARS + 1)
    r = owner.patch(f"/projects/{draft['id']}", json={"description": too_long})
    assert r.status_code == 400 and "too long" in r.json()["detail"]
    r = owner.post("/projects", data={"title": "T", "address": "A", "bid_deadline": DEADLINE, "description": too_long})
    assert r.status_code == 400
    # Exactly at the limit is accepted.
    assert owner.patch(f"/projects/{draft['id']}", json={"description": "ب" * MAX_SCOPE_CHARS}).status_code == 200


def test_scope_respects_ownership_and_reaches_providers_unchanged_once_published(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sp@example.com")
    other = _verified(db, "owner", "other@example.com")

    draft = _draft(owner, description=SCOPE)
    assert other.patch(f"/projects/{draft['id']}", json={"description": "x"}).status_code == 404
    assert sp.get(f"/projects/{draft['id']}").status_code == 404  # private while a draft

    published = _draft(owner, description=SCOPE, status="open")
    assert sp.get(f"/projects/{published['id']}").json()["description"] == SCOPE

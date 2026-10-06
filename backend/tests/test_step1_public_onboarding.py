"""Step 1 of the visitor journey: everything the public homepage needs to
explain both roles before signup -- the live document checklist per role,
the real subscription prices, and admin-editable role copy."""
from types import SimpleNamespace

import stripe
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from app.routers import public as public_router


def _admin_client(db) -> TestClient:
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    client = TestClient(app)
    assert client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"}).status_code == 200
    return client


def test_public_requirements_follow_admin_edits(db):
    admin = _admin_client(db)
    anon = TestClient(app)

    r = admin.post("/admin/requirements", json={"name": "Civil ID", "is_required": True, "applies_to": "owner"})
    assert r.status_code == 201, r.text
    req_id = r.json()["id"]
    admin.post("/admin/requirements", json={"name": "Commercial License", "applies_to": "contractor"})

    owner_docs = anon.get("/public/requirements", params={"role": "owner"}).json()
    assert [d["name"] for d in owner_docs] == ["Civil ID"]
    assert [d["name"] for d in anon.get("/public/requirements", params={"role": "contractor"}).json()] == ["Commercial License"]
    assert anon.get("/public/requirements", params={"role": "admin"}).status_code == 400

    # Rename + describe, then retire: the public checklist follows each edit.
    r = admin.patch(f"/admin/requirements/{req_id}", json={"name": "National ID", "description": "Any government ID"})
    assert r.status_code == 200 and r.json()["name"] == "National ID"
    assert anon.get("/public/requirements", params={"role": "owner"}).json() == [
        {"name": "National ID", "description": "Any government ID", "is_required": True}
    ]
    assert admin.patch(f"/admin/requirements/{req_id}", json={"name": "  "}).status_code == 400
    admin.patch(f"/admin/requirements/{req_id}", json={"is_active": False})
    assert anon.get("/public/requirements", params={"role": "owner"}).json() == []


def test_public_pricing_reads_configured_stripe_prices(monkeypatch):
    settings = public_router.get_settings()
    monkeypatch.setattr(public_router, "_pricing_cache", None)
    anon = TestClient(app)

    # Billing not configured -> no plans, never an error.
    monkeypatch.setattr(settings, "stripe_secret_key", None)
    assert anon.get("/public/pricing").json() == {"plans": []}

    monkeypatch.setattr(public_router, "_pricing_cache", None)
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(settings, "stripe_price_id_monthly", "price_m")
    monkeypatch.setattr(settings, "stripe_price_id_annual", "price_a")
    prices = {
        "price_m": {"currency": "usd", "unit_amount": 7900, "recurring": {"interval": "month", "interval_count": 1}},
        "price_a": {"currency": "kwd", "unit_amount": 250000, "recurring": {"interval": "year", "interval_count": 1}},
    }
    calls = []

    def fake_retrieve(price_id):
        calls.append(price_id)
        return prices[price_id]

    monkeypatch.setattr(stripe.Price, "retrieve", staticmethod(fake_retrieve))
    plans = anon.get("/public/pricing").json()["plans"]
    assert [(p["plan"], float(p["amount"]), p["currency"], p["interval"]) for p in plans] == [
        ("monthly", 79.0, "usd", "month"),
        ("annual", 250.0, "kwd", "year"),  # three-decimal currency
    ]
    anon.get("/public/pricing")
    assert len(calls) == 2  # second request served from cache

    # Stripe failure degrades to "no plans" rather than a 500.
    monkeypatch.setattr(public_router, "_pricing_cache", None)
    monkeypatch.setattr(stripe.Price, "retrieve", staticmethod(lambda _id: (_ for _ in ()).throw(RuntimeError("down"))))
    r = anon.get("/public/pricing")
    assert r.status_code == 200 and r.json() == {"plans": []}


def test_role_copy_is_admin_editable_and_listed_in_page_order(db):
    admin = _admin_client(db)
    anon = TestClient(app)

    cms = anon.get("/public/cms", params={"language": "en"}).json()
    for key in ("home_owner_title", "home_provider_title", "home_provider_cost", "signup_provider_hint"):
        assert cms[key], key

    keys = [e["key"] for e in admin.get("/admin/cms").json()]
    assert keys[:2] == ["hero_heading", "hero_subheading"]
    assert keys.index("home_owner_title") < keys.index("home_provider_title")

    admin.put("/admin/cms/home_provider_title/en", json={"value": "Contractor"})
    assert anon.get("/public/cms", params={"language": "en"}).json()["home_provider_title"] == "Contractor"


def test_signup_handoff_persists_the_chosen_role(db):
    """Step 1 -> Step 2 boundary: the account exists, the role the visitor
    chose is what the backend stored, and the user can authenticate."""
    from app.models.contractor import ContractorProfile
    from app.models.owner import OwnerProfile

    for role, email, extra in (
        ("owner", "own@example.com", {}),
        ("contractor", "sp@example.com", {"company_name": "Acme"}),  # "service_provider" in public links
    ):
        signup = TestClient(app)
        r = signup.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role, **extra})
        assert r.status_code == 201, r.text
        assert r.json()["role"] == role
        user_id = r.json()["id"]
        assert db.get(User, user_id).role.value == role
        profile_model = OwnerProfile if role == "owner" else ContractorProfile
        assert db.get(profile_model, user_id) is not None
        assert signup.get("/auth/me").json()["role"] == role

        fresh = TestClient(app)
        assert fresh.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
        assert fresh.get("/auth/me").json()["role"] == role

    anon = TestClient(app)
    base = {"email": "x@example.com", "password": "password123", "full_name": "X"}
    assert anon.post("/auth/signup", json=base).status_code == 422  # no role -> never guessed
    assert anon.post("/auth/signup", json={**base, "role": "admin"}).status_code == 400
    assert anon.post("/auth/signup", json={**base, "role": "service_provider"}).status_code == 422

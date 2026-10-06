"""Stage 3.9: a requirement may narrow who can respond -- organizations only,
and/or a platform-approved provider document -- on top of (never instead of)
platform verification. The same rule decides what a provider is told and what
the server enforces. A Kuwait example: an electrical fit-out that needs the
platform's (admin-configured) "Electrical works licence"."""
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.document import DocumentRequirement, ServiceProviderDocument
from app.models.enums import DocumentStatus, UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat()


def _owner(db) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": "owner@example.com", "password": "password123", "full_name": "N", "role": "owner"})
    c.put("/account/stakeholder", json={"type": "individual"})
    db.get(OwnerProfile, r.json()["id"]).verification_status = VerificationStatus.approved
    db.commit()
    return c


def _provider(db, email: str, organization: bool, licence=None, verified=True) -> TestClient:
    """licence: None (not held), a DocumentRequirement (approved, no expiry),
    or (requirement, expires_on)."""
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": "service_provider"})
    if organization:
        c.put("/account/stakeholder", json={"type": "organization", "legal_name": f"{email.split('@')[0]} W.L.L.", "authorized": True})
    else:
        c.put("/account/stakeholder", json={"type": "individual"})
    profile = db.get(ServiceProviderProfile, r.json()["id"])
    profile.company_name = email.split("@")[0]
    profile.payment_override_active = True
    profile.verification_status = VerificationStatus.approved if verified else VerificationStatus.pending_review
    if licence is not None:
        req, expires = licence if isinstance(licence, tuple) else (licence, None)
        # The verification checklist row (created at onboarding), approved by the platform.
        doc = db.query(ServiceProviderDocument).filter_by(service_provider_id=profile.user_id, requirement_id=req.id).first()
        if doc is None:
            doc = ServiceProviderDocument(service_provider_id=profile.user_id, requirement_id=req.id)
            db.add(doc)
        doc.status, doc.expires_on = DocumentStatus.approved, expires
    db.commit()
    return c


def _licence(db) -> DocumentRequirement:
    # Configured by a platform admin, as an optional provider document.
    req = DocumentRequirement(name="Electrical works licence", is_required=False, applies_to=UserRole.service_provider)
    db.add(req)
    db.add(DocumentRequirement(name="Owner title deed", is_required=True, applies_to=UserRole.owner))  # not offered
    db.commit()
    return req


def _publish(owner: TestClient, eligibility: dict | None) -> str:
    pid = owner.post("/projects", data={"title": "Villa electrical fit-out", "address": "Block 4, Street 12, Salwa", "bid_deadline": DEADLINE}).json()["id"]
    if eligibility is not None:
        assert owner.put(f"/projects/{pid}/eligibility", json=eligibility).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def test_owner_sets_eligibility_on_the_draft_and_it_persists(db):
    licence = _licence(db)
    owner = _owner(db)
    options = owner.get("/owner/eligibility-qualifications").json()
    assert [o["name"] for o in options] == ["Electrical works licence"]  # provider documents only

    pid = owner.post("/projects", data={"title": "Fit-out", "address": "Salwa", "bid_deadline": DEADLINE}).json()["id"]
    assert owner.get(f"/projects/{pid}").json()["provider_eligibility"] == {"provider_type": "any", "qualifications": []}
    assert owner.put(f"/projects/{pid}/eligibility", json={"qualifications": ["not-a-real-id"]}).status_code == 400
    r = owner.put(f"/projects/{pid}/eligibility", json={"provider_type": "organization", "qualifications": [licence.id]})
    assert r.status_code == 200

    again = TestClient(app)
    again.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    saved = again.get(f"/projects/{pid}").json()
    assert saved["status"] == "draft"
    assert saved["provider_eligibility"]["provider_type"] == "organization"
    assert [q["name"] for q in saved["provider_eligibility"]["qualifications"]] == ["Electrical works licence"]

    # Fixed once published: providers decide whether to respond on these terms.
    assert again.post(f"/owner/projects/{pid}/publish").status_code == 200
    assert again.put(f"/projects/{pid}/eligibility", json={}).status_code == 409


def test_eligible_provider_responds_and_ineligible_one_cannot_bypass_the_api(db):
    licence = _licence(db)
    owner = _owner(db)
    pid = _publish(owner, {"provider_type": "organization", "qualifications": [licence.id]})
    suitable = _provider(db, "noor@example.com", organization=True, licence=licence)
    individual = _provider(db, "sami@example.com", organization=False)
    expired = _provider(db, "gulf@example.com", organization=True, licence=(licence, date.today() - timedelta(days=1)))

    # 1. A verified, suitable provider sees it, opens it and responds.
    card = next(p for p in suitable.get("/service-provider/feed").json() if p["id"] == pid)
    assert card["eligible"] is True and card["ineligible_reasons"] == []
    assert suitable.get(f"/projects/{pid}").status_code == 200
    assert suitable.post(f"/projects/{pid}/offers", json={"amount": "2450.500"}).status_code == 200

    # 2. The listing stays visible with the reasons; everything past it is refused server-side.
    card = next(p for p in individual.get("/service-provider/feed").json() if p["id"] == pid)
    assert card["eligible"] is False and card["address"] is None
    assert any("organization" in r for r in card["ineligible_reasons"])
    assert any("Electrical works licence" in r for r in card["ineligible_reasons"])
    assert individual.get(f"/projects/{pid}/eligibility").json()["eligible"] is False
    assert individual.get(f"/projects/{pid}").status_code == 404  # no address, scope or drawings
    assert individual.get(f"/projects/{pid}/drawings-zip").status_code == 404
    assert individual.post(f"/projects/{pid}/clarifications", json={"question": "Is the DB board included?"}).status_code == 404
    r = individual.post(f"/projects/{pid}/offers", json={"amount": "1900"})
    assert r.status_code == 403 and "organization" in r.json()["detail"]

    r = expired.post(f"/projects/{pid}/offers", json={"amount": "2000"})
    assert r.status_code == 403 and "expired on" in r.json()["detail"]
    reasons = expired.get(f"/projects/{pid}/eligibility").json()["reasons"]
    assert len(reasons) == 1 and "expired" in reasons[0]  # organization part is satisfied

    # The owner only ever receives offers from eligible providers.
    assert [o["service_provider_company_name"] for o in owner.get(f"/owner/projects/{pid}/offers").json()] == ["noor"]


def test_no_restriction_means_no_one_is_blocked_and_lapses_stop_only_new_offers(db):
    licence = _licence(db)
    owner = _owner(db)
    # 3. Without restrictions, an individual with no extra documents responds.
    open_pid = _publish(owner, None)
    individual = _provider(db, "sami@example.com", organization=False)
    card = next(p for p in individual.get("/service-provider/feed").json() if p["id"] == open_pid)
    assert card["eligible"] is True
    assert individual.post(f"/projects/{open_pid}/offers", json={"amount": "800"}).status_code == 200

    # A provider who already bid and whose licence then expires keeps sight of
    # their own bid (and can withdraw), but can't revise it.
    pid = _publish(owner, {"qualifications": [licence.id]})
    holder = _provider(db, "noor@example.com", organization=False, licence=licence)
    assert holder.post(f"/projects/{pid}/offers", json={"amount": "1000"}).status_code == 200
    holder_id = db.query(ServiceProviderProfile).filter(ServiceProviderProfile.company_name == "noor").one().user_id
    doc = db.query(ServiceProviderDocument).filter_by(service_provider_id=holder_id, requirement_id=licence.id).one()
    doc.expires_on = date.today() - timedelta(days=1)
    db.commit()
    assert holder.get(f"/projects/{pid}").status_code == 200
    assert holder.post(f"/projects/{pid}/offers", json={"amount": "950"}).status_code == 403
    assert holder.post(f"/projects/{pid}/offers/withdraw").status_code == 200


def test_platform_verification_still_applies_independently(db):
    licence = _licence(db)
    owner = _owner(db)
    pid = _publish(owner, {"qualifications": [licence.id]})
    # 5. Holding the qualification never stands in for platform verification.
    pending = _provider(db, "new@example.com", organization=True, licence=licence, verified=False)
    assert pending.get("/service-provider/feed").status_code == 403
    assert pending.get(f"/projects/{pid}").status_code == 404
    assert pending.post(f"/projects/{pid}/offers", json={"amount": "1000"}).status_code == 403
    assert pending.get(f"/projects/{pid}/eligibility").status_code == 403

    # And a verified provider whose marketplace access lapses loses access even if eligible.
    eligible = _provider(db, "noor@example.com", organization=True, licence=licence)
    profile = db.query(ServiceProviderProfile).filter(ServiceProviderProfile.company_name == "noor").one()
    profile.payment_override_active = False
    db.commit()
    assert eligible.get(f"/projects/{pid}").status_code == 404
    assert eligible.post(f"/projects/{pid}/offers", json={"amount": "1000"}).json()["detail"] == "payment_required"

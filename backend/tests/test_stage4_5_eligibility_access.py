"""Stage 4.5: whether a provider can take part in a requirement, and if not
why, is one server-side answer (participation) -- the same checks the offer
endpoints enforce -- telling lifecycle, platform standing, this
requirement's conditions and marketplace access apart, and which problems the
provider can put right."""
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.category import ServiceCategory
from app.models.document import DocumentRequirement, ServiceProviderDocument
from app.models.enums import DocumentStatus, UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _account(role, email, organization=None, joining=False):
    c = TestClient(app)
    uid = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role}).json()["id"]
    if not joining:  # someone joining an organization doesn't establish their own stakeholder
        c.put("/account/stakeholder", json={"type": "organization", "legal_name": organization, "authorized": True} if organization else {"type": "individual"})
    return c, uid


def _approve(db, uid, role="service_provider", paid=True):
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    p = db.get(model, uid)
    p.verification_status = VerificationStatus.approved
    if role == "service_provider":
        p.company_name = p.company_name or "Co"
        p.payment_override_active = paid
    db.commit()


def _hold(db, uid, licence, expires=None):
    d = db.query(ServiceProviderDocument).filter_by(service_provider_id=uid, requirement_id=licence.id).first() or ServiceProviderDocument(service_provider_id=uid, requirement_id=licence.id)
    d.status, d.expires_on = DocumentStatus.approved, expires
    db.add(d)
    db.commit()


def _setup(db):
    licence = DocumentRequirement(name="Electrical works licence", is_required=False, applies_to=UserRole.service_provider)
    electrical = ServiceCategory(name="Electrical", is_active=True)
    db.add_all([licence, electrical])
    db.commit()
    owner, owner_id = _account("owner", "owner@example.com")
    _approve(db, owner_id, "owner")
    pid = owner.post("/projects", data={"title": "Villa rewiring", "address": "Kaifan", "governorate": "capital", "category_id": electrical.id, "description": "Rewire a villa.", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{pid}/eligibility", json={"qualifications": [licence.id], "match_category": True, "match_governorate": True})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return owner, pid, licence, electrical


def _verdict(client, pid):
    detail = client.get(f"/projects/{pid}")
    if detail.status_code == 200:
        return detail.json()["participation"]
    return client.get(f"/projects/{pid}/eligibility").json()["participation"]


def _provider(db, email, licence, electrical, organization=None, paid=True, govs=("capital",)):
    c, uid = _account("service_provider", email, organization)
    _approve(db, uid, paid=paid)
    c.put("/service-provider/services", json={"categories": [electrical.id], "governorates": list(govs)})
    _hold(db, uid, licence)
    return c, uid


def test_eligible_unverified_wrong_category_area_and_qualification(db):
    owner, pid, licence, electrical = _setup(db)
    # 1. Verified and eligible: can take part, and does.
    good, _ = _provider(db, "good@example.com", licence, electrical)
    assert _verdict(good, pid) == {"status": "can_participate", "action": None, "availability": "open"}
    assert good.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 200
    # 2. Not verified: no way round it.
    pending, _ = _account("service_provider", "pending@example.com")
    assert pending.get(f"/projects/{pid}").status_code in (403, 404)
    assert pending.get(f"/projects/{pid}/eligibility").status_code == 403
    assert pending.post(f"/projects/{pid}/offers", json={"amount": "1"}).status_code == 403
    # 3-5. Wrong type of work / outside the area / missing qualification: told which, and what they can fix.
    wrong, wid = _account("service_provider", "wrong@example.com")
    _approve(db, wid)
    wrong.put("/service-provider/services", json={"categories": [], "governorates": ["jahra"]})
    r = wrong.get(f"/projects/{pid}/eligibility").json()
    assert r["participation"]["status"] == "not_eligible"
    assert {(x["code"], x["fixable"]) for x in r["reasons"]} == {("category_not_offered", True), ("governorate_not_served", True), ("qualification_missing", True)}
    for attempt in ({"amount": "800"}, {"amount": "800", "eligible": True}, {"amount": "800", "service_provider_id": wid}):
        assert wrong.post(f"/projects/{pid}/offers", json=attempt).status_code == 403  # 8. no request shape gets past it
    assert wrong.get(f"/projects/{pid}").status_code == 404
    # Putting it right (truthfully) opens it -- nothing else needed.
    wrong.put("/service-provider/services", json={"categories": [electrical.id], "governorates": ["capital"]})
    _hold(db, wid, licence)
    assert _verdict(wrong, pid)["status"] == "can_participate"
    # A requirement for organizations only: an individual can't fix that.
    org_pid = owner.post("/projects", data={"title": "Substation", "address": "x", "description": "HV works.", "bid_deadline": _when(9)}).json()["id"]
    owner.put(f"/projects/{org_pid}/eligibility", json={"provider_type": "organization"})
    owner.post(f"/owner/projects/{org_pid}/publish")
    r = good.get(f"/projects/{org_pid}/eligibility").json()
    assert [(x["code"], x["fixable"]) for x in r["reasons"]] == [("organization_only", False)]
    # Verified and eligible, but marketplace access not active: one action, named.
    unpaid, _ = _provider(db, "unpaid@example.com", licence, electrical, paid=False)
    assert unpaid.get(f"/projects/{pid}/eligibility").json()["participation"] == {"status": "action_required", "action": "activate_access", "availability": "open"}
    assert unpaid.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 403


def test_an_organization_takes_part_as_one_and_only_through_its_members(db):
    owner, pid, licence, electrical = _setup(db)
    admin, admin_id = _account("service_provider", "boss@gulf.example", "Gulf Electrical W.L.L.")
    _approve(db, admin_id)
    admin.put("/service-provider/services", json={"categories": [electrical.id], "governorates": ["capital"]})
    _hold(db, admin_id, licence)  # the organization's licence, held by its representative
    member, member_id = _account("service_provider", "eng@gulf.example", joining=True)
    token = admin.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    invited_not_joined, _ = _account("service_provider", "later@gulf.example", joining=True)
    admin.post("/account/organization/invitations", json={"email": "later@gulf.example"})
    assert member.post(f"/account/invitations/{token}/accept").status_code == 200

    # 6. Every member gets the organization's answer -- its verification, services and licence.
    assert _verdict(admin, pid)["status"] == _verdict(member, pid)["status"] == "can_participate"
    assert member.post(f"/projects/{pid}/offers", json={"amount": "950"}).status_code == 200
    assert admin.get(f"/projects/{pid}/offers/mine").json()["amount"] == "950.000"  # one offer, the organization's
    # 7. Someone invited but not joined acts for no one.
    assert invited_not_joined.post(f"/projects/{pid}/offers/withdraw").status_code in (403, 404)
    assert invited_not_joined.get(f"/projects/{pid}/offers/mine").status_code == 403  # not verified as anyone
    assert invited_not_joined.get(f"/projects/{pid}").status_code in (403, 404)
    # A member who leaves loses the organization's rights at once.
    members = admin.get("/account/organization/members").json()
    leaving = next(m for m in members if m["email"] == "eng@gulf.example")
    assert admin.delete(f"/account/organization/members/{leaving['user_id']}").status_code == 200
    assert member.post(f"/projects/{pid}/offers/withdraw").status_code in (403, 404)
    assert admin.get(f"/projects/{pid}/offers/mine").json()["status"] == "submitted"
    # Another organization sees none of it.
    other, other_id = _provider(db, "rival@example.com", licence, electrical, organization="Rival Co")
    assert other.get(f"/projects/{pid}/offers/mine").json() is None


def test_lifecycle_comes_first(db):
    owner, pid, licence, electrical = _setup(db)
    good, _ = _provider(db, "good@example.com", licence, electrical)
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="A"))
    db.commit()
    admin = TestClient(app)
    admin.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    # Paused by the owner: eligible, but not now.
    owner.post(f"/owner/projects/{pid}/pause", json={"reason": "Waiting for the permit."})
    assert _verdict(good, pid) == {"status": "unavailable", "action": None, "availability": "paused"}
    owner.post(f"/owner/projects/{pid}/resume")
    # 9. Hidden by U-Tender: unavailable, and nothing about it or why.
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True})
    r = good.get(f"/projects/{pid}/eligibility").json()
    assert r["participation"] == {"status": "unavailable", "action": None, "availability": "unavailable"} and r["listing"] is None and r["reasons"] == []
    assert good.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 400
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": False})
    # 10. Past the deadline: eligibility doesn't reopen it.
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert good.get(f"/projects/{pid}/eligibility").json()["participation"] == {"status": "unavailable", "action": None, "availability": "ended"}
    assert good.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 400


def test_the_rules_providers_are_held_to_are_the_published_ones(db):
    owner, pid, licence, electrical = _setup(db)
    good, _ = _provider(db, "good@example.com", licence, electrical)
    # 11. Conditions can't be changed under providers once published; the current rules are the ones applied.
    assert owner.put(f"/projects/{pid}/eligibility", json={"provider_type": "organization"}).status_code == 409
    shown = good.get(f"/projects/{pid}").json()["provider_eligibility"]
    assert shown["provider_type"] == "any" and [q["name"] for q in shown["qualifications"]] == ["Electrical works licence"]
    # 12. Nothing outside the rules blocks an eligible provider: an empty profile field, a page reload.
    assert _verdict(good, pid)["status"] == "can_participate" and good.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 200

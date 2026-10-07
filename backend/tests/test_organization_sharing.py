"""Everything done for an organization is shared by its members: an owner
organization's requirements, and a provider organization's offers,
attachments and questions. A member who leaves loses access; the
organization keeps its work."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat() + "Z"


def _account(role: str, email: str) -> tuple[TestClient, str]:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": email.split("@")[0].title(), "role": role})
    return c, r.json()["id"]


def _approve(db, role: str, user_id: str):
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, user_id)
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.payment_override_active = True
    db.commit()


def _organization(db, role: str, name: str, admin_email: str, member_email: str):
    admin, admin_id = _account(role, admin_email)
    assert admin.put("/account/stakeholder", json={"type": "organization", "legal_name": name, "authorized": True}).status_code == 200
    member, member_id = _account(role, member_email)
    # The representative invites by email; the colleague joins by accepting.
    r = admin.post("/account/organization/invitations", json={"email": member_email.upper(), "position": "Projects engineer"})
    assert r.status_code == 201, r.text
    token = r.json()["link"].rsplit("/", 1)[-1]
    assert member.post(f"/account/invitations/{token}/accept").status_code == 200
    assert [m["role"] for m in admin.get("/account/organization/members").json()] == ["admin", "member"]
    _approve(db, role, admin_id)  # the organization is verified once; members share it
    return admin, member, admin_id, member_id


def test_owner_organization_members_share_requirements(db):
    fahad, noura, fahad_id, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    pid = fahad.post("/projects", data={"title": "Warehouse roof", "address": "Shuwaikh", "bid_deadline": DEADLINE}).json()["id"]

    # Noura sees and continues the organization's draft, and can publish it.
    assert [p["id"] for p in noura.get("/owner/projects").json()] == [pid]
    version = noura.get(f"/projects/{pid}").json()["version"]
    assert noura.patch(f"/projects/{pid}", json={"description": "Replace sheeting"}, headers={"If-Match": str(version)}).status_code == 200
    assert noura.post(f"/owner/projects/{pid}/publish").status_code == 200

    # A provider's question notifies every member; either can answer.
    sp, sp_id = _account("service_provider", "sp@example.com")
    sp.put("/account/stakeholder", json={"type": "individual"})
    _approve(db, "service_provider", sp_id)
    db.get(ServiceProviderProfile, sp_id).company_name = "Roofing Co"
    db.commit()
    q = sp.post(f"/projects/{pid}/clarifications", json={"question": "Insulated panels?"}).json()
    notified = {n.user_id for n in db.query(Notification).filter(Notification.type == "clarification_asked")}
    assert notified == {fahad_id, noura_id}
    assert fahad.post(f"/projects/{pid}/clarifications/{q['id']}/answer", json={"answer": "Yes, 50 mm."}).status_code == 200

    # Others still can't; a removed member loses access, the organization keeps it.
    outsider, _ = _account("owner", "outsider@example.com")
    assert outsider.get(f"/projects/{pid}").status_code == 404
    assert noura.post("/account/organization/invitations", json={"email": "outsider@example.com"}).status_code == 403  # only the representative
    assert fahad.delete(f"/account/organization/members/{noura_id}").status_code == 200
    assert noura.get(f"/projects/{pid}").status_code == 404
    assert fahad.get(f"/projects/{pid}").status_code == 200


def test_provider_organization_members_share_one_offer(db):
    owner, owner_id = _account("owner", "owner@example.com")
    owner.put("/account/stakeholder", json={"type": "individual"})
    _approve(db, "owner", owner_id)
    pid = owner.post("/projects", data={"title": "Fit-out", "address": "Salmiya", "bid_deadline": DEADLINE, "status": "open"}).json()["id"]
    owner.put  # (published directly as open)

    sami, ali, sami_id, ali_id = _organization(db, "service_provider", "Sami Contracting Co.", "sami@sc.example", "ali@sc.example")
    assert sami.post(f"/projects/{pid}/offers", json={"amount": "4200", "message": "Sami's first pass"}).status_code == 200

    # Ali works on the same offer: sees it, revises it -- no second offer.
    mine = ali.get(f"/projects/{pid}/offers/mine").json()
    assert mine["message"] == "Sami's first pass"
    assert ali.post(f"/projects/{pid}/offers", json={"amount": "4100", "message": "Ali's revision"}).status_code == 200
    assert db.query(Offer).filter(Offer.project_id == pid).count() == 1
    assert sami.get(f"/projects/{pid}/offers/mine").json()["amount"] == "4100.000"
    assert len(ali.get("/service-provider/my-bids").json()) == 1
    # The owner receives one offer, from the organization (not from a person).
    offers = owner.get(f"/owner/projects/{pid}/offers").json()
    assert [o["service_provider_company_name"] for o in offers] == ["Sami Contracting Co."]
    # Ali acts as the organization: its identity, verification and payment.
    acting = ali.get("/account/identity").json()["acting_as"]
    assert acting["kind"] == "organization" and acting["name"] == "Sami Contracting Co."
    assert ali.get("/service-provider/profile").json()["user_id"] == sami_id
    # Either member can withdraw it.
    assert sami.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert ali.get(f"/projects/{pid}/offers/mine").json()["status"] == "withdrawn"


def test_invitations(db):
    admin, _member, _a, _m = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    invite = lambda email: admin.post("/account/organization/invitations", json={"email": email})  # noqa: E731

    # Someone without an account yet: invited by email, signs up, then accepts.
    r = invite("khalid@gulf.example")
    assert r.status_code == 201
    token = r.json()["link"].rsplit("/", 1)[-1]
    seen = TestClient(app).get(f"/account/invitations/{token}").json()  # the link, before signing in
    assert seen["organization_name"] == "Gulf Holdings W.L.L." and seen["account_exists"] is False and seen["role"] == "owner"
    assert invite("khalid@gulf.example").status_code == 409  # already pending
    assert [i["email"] for i in admin.get("/account/organization/invitations").json()] == ["khalid@gulf.example"]

    wrong, _ = _account("owner", "someone.else@example.com")
    assert wrong.post(f"/account/invitations/{token}/accept").status_code == 403  # a different email
    khalid, _ = _account("owner", "khalid@gulf.example")
    assert khalid.post(f"/account/invitations/{token}/accept").json()["acting_as"]["name"] == "Gulf Holdings W.L.L."
    assert khalid.post(f"/account/invitations/{token}/accept").status_code == 404  # used once

    # Withdrawn and expired links stop working.
    r = invite("late@gulf.example")
    admin.delete(f"/account/organization/invitations/{r.json()['id']}")
    late, _ = _account("owner", "late@gulf.example")
    assert late.post(f"/account/invitations/{r.json()['link'].rsplit('/', 1)[-1]}/accept").status_code == 404
    from app.models.organization import OrganizationInvitation

    r = invite("old@gulf.example")
    row = db.get(OrganizationInvitation, r.json()["id"])
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert TestClient(app).get(f"/account/invitations/{r.json()['link'].rsplit('/', 1)[-1]}").status_code == 404

    # Who can't be invited or join.
    _account("service_provider", "provider@example.com")
    assert invite("provider@example.com").status_code == 400  # other side of the marketplace
    verified, verified_id = _account("owner", "verified@example.com")
    verified.put("/account/stakeholder", json={"type": "individual"})
    _approve(db, "owner", verified_id)
    assert invite("verified@example.com").status_code == 409  # represents someone in its own right
    assert invite("noura@gulf.example").status_code == 409  # already a member
    assert _member.post("/account/organization/invitations", json={"email": "x@example.com"}).status_code == 403  # only the representative

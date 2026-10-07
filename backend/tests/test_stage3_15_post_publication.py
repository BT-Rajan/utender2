"""Stage 3.15: after publication the owner can pause, resume, extend, amend and
close early -- without corrupting the tender or treating it like a draft, and
without silently changing what providers have already priced."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import VerificationStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.project_amendment import ProjectAmendment
from app.models.service_provider import ServiceProviderProfile


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


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


def _published(owner: TestClient, days: float = 14) -> str:
    return owner.post(
        "/projects",
        data={"title": "Boundary wall", "address": "Sabah Al-Ahmad, plot 12", "governorate": "ahmadi", "description": "Build a 60 m block wall with a sliding gate.", "bid_deadline": _when(days), "status": "open"},
    ).json()["id"]


def _types(db, kind: str) -> int:
    return db.query(Notification).filter(Notification.type == kind).count()


def test_pause_and_resume(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    beta = _verified(db, "service_provider", "beta@example.com")
    pid = _published(owner)
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "5000"}).status_code == 200

    r = owner.post(f"/owner/projects/{pid}/pause", json={"reason": "Waiting for the municipality permit."})
    assert r.status_code == 200 and r.json()["paused_at"] and r.json()["status"] == "open"
    assert _types(db, "tender_paused") == 1  # the bidder is told
    # Providers see it is paused, and why -- in the list and when they open it.
    card = next(p for p in beta.get("/service-provider/feed").json() if p["id"] == pid)
    assert card["paused_at"] and card["pause_reason"] == "Waiting for the municipality permit."
    assert alpha.get(f"/projects/{pid}").json()["tender_rules"]["questions_open"] is False
    # Nothing is accepted while paused...
    assert beta.post(f"/projects/{pid}/offers", json={"amount": "4000"}).status_code == 400
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "4500"}).status_code == 400
    assert alpha.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    assert alpha.post(f"/projects/{pid}/clarifications", json={"question": "When?"}).status_code == 400
    # ...and nothing is lost.
    offer = db.query(Offer).one()
    assert str(offer.amount) == "5000.000" and offer.status.value == "submitted"
    assert owner.post(f"/owner/projects/{pid}/pause", json={"reason": "again"}).status_code == 400

    r = owner.post(f"/owner/projects/{pid}/resume")
    assert r.status_code == 200 and r.json()["paused_at"] is None and _types(db, "tender_resumed") == 1
    assert beta.post(f"/projects/{pid}/offers", json={"amount": "4000"}).status_code == 200

    # A pause that outlasts the deadline doesn't silently reopen it.
    owner.post(f"/owner/projects/{pid}/pause", json={"reason": "Site access blocked."})
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert owner.post(f"/owner/projects/{pid}/resume").status_code == 400
    assert owner.get(f"/projects/{pid}").json()["status"] == "closed"


def test_extend_the_deadline(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner, days=5)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "5000"})
    version = owner.get(f"/projects/{pid}").json()["version"]
    later = _when(12)
    r = owner.patch(f"/projects/{pid}", json={"bid_deadline": later, "reason": "More time for site visits."}, headers={"If-Match": str(version)})
    assert r.status_code == 200
    assert alpha.get(f"/projects/{pid}").json()["bid_deadline"] == later  # providers see it
    amendment = db.query(ProjectAmendment).one()
    assert amendment.deadline_extended and not amendment.material  # more time doesn't change what was priced
    assert db.query(Offer).one().based_on_material_revision == db.get(Project, pid).material_revision  # offer still current
    assert _types(db, "tender_amendment") == 1

    version = r.json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(-1)}, headers={"If-Match": str(version)}).status_code == 400  # past
    assert owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(6)}, headers={"If-Match": str(version)}).status_code == 400  # earlier, bids exist
    # The one deadline is what the server enforces.
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "4900"}).status_code == 400
    # Once closed, no extension reopens it.
    assert owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(20)}).status_code == 400


def test_material_changes_dont_silently_alter_submitted_offers(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner, days=10)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "5000", "message": "Priced for 60 m."})

    # A title correction is not material.
    v = owner.get(f"/projects/{pid}").json()["version"]
    r = owner.patch(f"/projects/{pid}", json={"title": "Boundary wall — plot 12"}, headers={"If-Match": str(v)})
    assert r.json()["material_revision"] == 0

    # A scope change is: recorded, announced, and the existing offer flagged -- not altered.
    r = owner.patch(f"/projects/{pid}", json={"description": "Build an 80 m block wall with two gates."}, headers={"If-Match": str(r.json()["version"])})
    assert r.status_code == 200 and r.json()["material_revision"] == 1
    assert db.query(ProjectAmendment).filter(ProjectAmendment.material.is_(True)).count() == 1
    mine = alpha.get(f"/projects/{pid}/offers/mine").json()
    assert mine["based_on_material_revision"] == 0 and mine["amount"] == "5000.000" and mine["message"] == "Priced for 60 m."
    flagged = owner.get(f"/owner/projects/{pid}/offers").json()[0]
    assert flagged["based_on_material_revision"] < r.json()["material_revision"]
    note = db.query(Notification).filter(Notification.type == "tender_amendment").order_by(Notification.created_at.desc()).first()
    assert "Review your offer" in note.body

    # The provider confirms it stands (or revises it).
    assert alpha.post(f"/projects/{pid}/offers/confirm").json()["based_on_material_revision"] == 1
    assert alpha.post(f"/projects/{pid}/offers/confirm").status_code == 400  # already current
    assert db.query(AuditLog).filter(AuditLog.action == "offer.confirmed").count() == 1

    # Adding a document after publication is a material amendment too.
    r = owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("gate-detail.pdf", b"%PDF", "application/pdf"))])
    assert r.status_code == 200 and r.json()["material_revision"] == 2
    # Items, response rules, eligibility and tender rules stay as published.
    v = r.json()["version"]
    assert owner.put(f"/projects/{pid}/items", json={"pricing_basis": "lump_sum", "items": []}, headers={"If-Match": str(v)}).status_code == 409
    assert owner.put(f"/projects/{pid}/eligibility", json={}, headers={"If-Match": str(v)}).status_code == 409

    # A material change needs time for providers to react.
    row = db.get(Project, pid)
    row.bid_deadline = datetime.utcnow() + timedelta(days=1)
    db.commit()
    v = owner.get(f"/projects/{pid}").json()["version"]
    r = owner.patch(f"/projects/{pid}", json={"description": "Build a 90 m wall."}, headers={"If-Match": str(v)})
    assert r.status_code == 400 and "3 days" in r.json()["detail"]
    assert owner.get(f"/projects/{pid}").json()["description"] == "Build an 80 m block wall with two gates."  # unchanged
    r = owner.patch(f"/projects/{pid}", json={"description": "Build a 90 m wall.", "bid_deadline": _when(7)}, headers={"If-Match": str(v)})
    assert r.status_code == 200 and r.json()["material_revision"] == 3


def test_close_early(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    beta = _verified(db, "service_provider", "beta@example.com")
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "5000"})
    before = datetime.utcnow().replace(microsecond=0)
    r = owner.post(f"/owner/projects/{pid}/close")
    assert r.status_code == 200 and r.json()["status"] == "closed"
    assert before <= datetime.fromisoformat(r.json()["closed_at"].rstrip("Z")) <= datetime.utcnow() + timedelta(seconds=1)
    assert db.query(AuditLog).filter(AuditLog.action == "project.close").count() == 1
    assert _types(db, "tender_closed") == 1
    assert beta.post(f"/projects/{pid}/offers", json={"amount": "4000"}).status_code == 400
    offer = db.query(Offer).one()
    assert str(offer.amount) == "5000.000" and offer.status.value == "submitted"  # preserved, not awarded
    assert alpha.get(f"/projects/{pid}").json()["status"] == "closed"  # the bidder sees it closed
    # Nothing more can be changed or added.
    assert owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("late.pdf", b"%PDF", "application/pdf"))]).status_code == 400
    assert owner.patch(f"/projects/{pid}", json={"title": "x"}).status_code == 400


def test_only_the_owner_side_controls_a_published_requirement(db):
    owner = _verified(db, "owner", "owner@example.com")
    other = _verified(db, "owner", "other@example.com")
    sp = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    for client, expected in ((sp, 403), (other, 404)):
        assert client.post(f"/owner/projects/{pid}/pause", json={"reason": "No reason"}).status_code == expected
        assert client.post(f"/owner/projects/{pid}/resume").status_code == expected
        assert client.post(f"/owner/projects/{pid}/close").status_code == expected
        assert client.patch(f"/projects/{pid}", json={"bid_deadline": _when(30), "description": "mine"}).status_code == 404
        assert client.post(f"/projects/{pid}/drawings", files=[("drawings", ("x.pdf", b"%PDF", "application/pdf"))]).status_code == 404
    row = db.get(Project, pid)
    assert (row.status.value, row.paused_at, row.material_revision, row.description) == ("open", None, 0, "Build a 60 m block wall with a sliding gate.")

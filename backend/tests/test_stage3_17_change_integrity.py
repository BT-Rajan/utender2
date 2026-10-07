"""Stage 3.17: once published, a requirement can be corrected, but a change to
what providers price is never silent -- the earlier version can still be read,
the change says who/when/what, providers are told, and every offer stays tied
to the version (and documents) it was priced against."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.notification import Notification
from app.models.offer import Offer, OfferRevision
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.project_amendment import ProjectAmendment
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User

SCOPE = "Build a 60 m block wall with a sliding gate."


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


def _published(owner: TestClient) -> str:
    return owner.post(
        "/projects",
        data={"title": "Boundary wal", "address": "Sabah Al-Ahmad, plot 12", "governorate": "ahmadi", "description": SCOPE, "bid_deadline": _when(10), "status": "open"},
        files=[("drawings", ("wall-plan.pdf", b"%PDF-v1", "application/pdf"))],
    ).json()["id"]


def _patch(owner, pid, body):
    v = owner.get(f"/projects/{pid}").json()["version"]
    return owner.patch(f"/projects/{pid}", json=body, headers={"If-Match": str(v)})


def _fetch(client, url):
    return client.get("/" + url.split("://", 1)[-1].split("/", 1)[-1]).content


def test_a_harmless_correction_restarts_nothing(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "5000"})
    r = _patch(owner, pid, {"title": "Boundary wall"})
    assert r.status_code == 200 and r.json()["material_revision"] == 0
    assert alpha.get(f"/projects/{pid}/offers/mine").json()["based_on_material_revision"] == 0  # still current, nothing to confirm
    a = db.query(ProjectAmendment).one()
    assert not a.material and a.changes == {"title": {"from": "Boundary wal", "to": "Boundary wall"}}
    # A correction of version 0 is part of version 0.
    assert alpha.get(f"/projects/{pid}/versions/0").json()["fields"]["title"] == "Boundary wall"


def test_a_material_change_keeps_what_was_published(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    watcher = _verified(db, "service_provider", "beta@example.com")
    _verified(db, "service_provider", "gamma@example.com")  # never involved
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "5000", "message": "Priced for 60 m."})
    watcher.post(f"/projects/{pid}/clarifications", json={"question": "Is the gate motorised?"})

    r = _patch(owner, pid, {"description": "Build an 80 m block wall with two gates.", "reason": "Neighbour plot added."})
    assert r.status_code == 200 and r.json()["material_revision"] == 1
    # Who, when, what -- and what it was.
    a = db.query(ProjectAmendment).one()
    owner_id = db.query(User).filter(User.email == "owner@example.com").one().id
    assert a.material and a.material_revision == 1 and a.created_by == owner_id and a.created_at and a.reason == "Neighbour plot added."
    assert a.changes == {"description": {"from": SCOPE, "to": "Build an 80 m block wall with two gates."}}
    listed = alpha.get(f"/projects/{pid}/amendments").json()[0]
    assert listed["changes"]["description"]["from"] == SCOPE and listed["material_revision"] == 1

    # The published version is still there to read, and the current one is marked.
    v0, v1 = alpha.get(f"/projects/{pid}/versions/0").json(), alpha.get(f"/projects/{pid}/versions/1").json()
    assert v0["fields"]["description"] == SCOPE and not v0["current"] and v0["superseded_at"] and v0["complete"]
    assert v1["fields"]["description"].startswith("Build an 80 m") and v1["current"] and v1["amendment_number"] == 1
    assert alpha.get(f"/projects/{pid}/versions/2").status_code == 404

    # The offer stays tied to the version it priced -- not presented as made against the new scope.
    mine = alpha.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["based_on_material_revision"], mine["message"]) == (0, "Priced for 60 m.")
    assert owner.get(f"/owner/projects/{pid}/offers").json()[0]["based_on_material_revision"] == 0

    # Told: the bidder (review your offer), and the provider who asked about it; nobody else.
    told = {db.get(ServiceProviderProfile, n.user_id).company_name: n.body for n in db.query(Notification).filter(Notification.type == "tender_amendment")}
    assert set(told) == {"alpha", "beta"} and "Review your offer" in told["alpha"] and "current version" in told["beta"]

    # Confirming moves it to the new version; the trail keeps that it was first made against version 0.
    alpha.post(f"/projects/{pid}/offers/confirm")
    assert db.query(Offer).one().based_on_material_revision == 1
    assert [r.based_on_material_revision for r in db.query(OfferRevision)] == [0]


def test_a_replaced_document_keeps_the_earlier_offers_context(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "5000"})
    r = owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("wall-plan.pdf", b"%PDF-v2", "application/pdf")), ("drawings", ("gate.pdf", b"%PDF-gate", "application/pdf"))])
    assert r.status_code == 200 and r.json()["material_revision"] == 1
    assert db.query(ProjectAmendment).one().changes == {"documents": {"added": ["gate.pdf"], "replaced": ["wall-plan.pdf"]}}

    # The current document is clear...
    now = {d["file_name"]: d for d in alpha.get(f"/projects/{pid}").json()["drawings"]}
    assert now["wall-plan.pdf"]["revision"] == 2 and _fetch(alpha, now["wall-plan.pdf"]["url"]) == b"%PDF-v2"
    # ...and the offer's version still shows -- and serves -- the file it was priced on.
    offer_version = alpha.get(f"/projects/{pid}/offers/mine").json()["based_on_material_revision"]
    then = alpha.get(f"/projects/{pid}/versions/{offer_version}").json()["documents"]
    assert [(d["file_name"], d["revision"]) for d in then] == [("wall-plan.pdf", 1)]
    assert _fetch(alpha, then[0]["url"]) == b"%PDF-v1"
    # Old files stay behind the same authorization: no access without seeing the requirement.
    assert TestClient(app).get(f"/projects/{pid}/versions/0").status_code in (401, 403)
    assert _verified(db, "owner", "other@example.com").get(f"/projects/{pid}/versions/0").status_code == 404


def test_unsafe_material_edits_are_blocked(db):
    owner = _verified(db, "owner", "owner@example.com")
    pid = _published(owner)
    v = owner.get(f"/projects/{pid}").json()["version"]
    # What offers are itemised and priced against, and who may respond, stay as published.
    assert owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [{"description": "Blockwork", "quantity": "200", "unit": "m²"}]}, headers={"If-Match": str(v)}).status_code == 409
    assert owner.put(f"/projects/{pid}/eligibility", json={"provider_type": "organization"}, headers={"If-Match": str(v)}).status_code == 409
    assert owner.put(f"/projects/{pid}/response-requirements", json={"completion_period": "required"}, headers={"If-Match": str(v)}).status_code == 409
    # Documents providers may have priced on can't be removed or relabelled.
    doc = owner.get(f"/projects/{pid}").json()["drawings"][0]["id"]
    assert owner.delete(f"/projects/{pid}/drawings/{doc}").status_code == 409
    # Too close to the deadline: the existing 3.15 rule -- extend it in the same change.
    db.get(Project, pid).bid_deadline = datetime.utcnow() + timedelta(days=1)
    db.commit()
    assert _patch(owner, pid, {"description": "Changed."}).status_code == 400
    assert _patch(owner, pid, {"description": "Changed.", "bid_deadline": _when(8)}).status_code == 200
    # A stale page can't overwrite a newer version.
    assert owner.patch(f"/projects/{pid}", json={"description": "From an old tab."}, headers={"If-Match": "1"}).status_code == 409
    assert db.query(ProjectAmendment).count() == 1


def test_only_the_owner_side_and_never_once_ended(db):
    owner = _verified(db, "owner", "owner@example.com")
    other = _verified(db, "owner", "other@example.com")
    sp = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    assert other.patch(f"/projects/{pid}", json={"description": "Mine now."}).status_code == 404
    assert sp.patch(f"/projects/{pid}", json={"description": "Mine now."}).status_code == 404
    assert sp.post(f"/projects/{pid}/drawings", files=[("drawings", ("x.pdf", b"%PDF", "application/pdf"))]).status_code == 404
    owner.post(f"/owner/projects/{pid}/close-externally")
    assert _patch(owner, pid, {"description": "After the end."}).status_code == 400
    assert _patch(owner, pid, {"title": "Typo fix"}).status_code == 400
    assert owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("late.pdf", b"%PDF", "application/pdf"))]).status_code == 400
    row = db.get(Project, pid)
    assert (row.status.value, row.description, row.material_revision) == ("no_award", SCOPE, 0)
    assert db.query(ProjectAmendment).count() == 0

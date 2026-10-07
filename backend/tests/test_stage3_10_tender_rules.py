"""Stage 3.10: the rules of participation are set on the draft, shown to
providers, and are the same rules the server enforces. A Kuwait example:
boundary fencing for a plot in Sabah Al-Ahmad, offers close in 14 days,
questions until day 10."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile

NOW = datetime.utcnow().replace(microsecond=0)
DEADLINE = NOW + timedelta(days=14)
TERMS = "Payment: 30% on mobilisation, 60% on progress, 10% retained for 6 months.\nPrices valid for 90 days."
INSTRUCTIONS = "Site visits by appointment only; call the guard on 9xxxxxxx. Fence line is marked with pegs."


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


def _draft(owner: TestClient) -> str:
    return owner.post(
        "/projects", data={"title": "Boundary fencing", "address": "Sabah Al-Ahmad, plot 12", "bid_deadline": DEADLINE.isoformat() + "Z"}
    ).json()["id"]


def test_owner_defines_rules_on_the_draft_and_they_persist(db):
    owner = _verified(db, "owner", "owner@example.com")
    pid = _draft(owner)
    rules = owner.get(f"/projects/{pid}").json()["tender_rules"]
    assert rules["questions_allowed"] is True and rules["questions_deadline"] is None  # defaults: questions until offers close

    cutoff = (NOW + timedelta(days=10)).replace(hour=14)  # 17:00 in Kuwait
    body = {
        "tender_type": "sealed",
        "questions_allowed": True,
        "questions_deadline": cutoff.isoformat() + "+00:00",
        "commercial_terms": TERMS,
        "bidder_instructions": INSTRUCTIONS,
    }
    assert owner.put(f"/projects/{pid}/tender-rules", json=body).status_code == 200

    again = TestClient(app)
    again.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    saved = again.get(f"/projects/{pid}").json()
    assert saved["status"] == "draft" and saved["tender_type"] == "sealed"
    assert saved["tender_rules"]["questions_deadline"] == cutoff.isoformat() + "Z"
    assert saved["tender_rules"]["commercial_terms"] == TERMS and saved["tender_rules"]["bidder_instructions"] == INSTRUCTIONS
    assert saved["description"] is None  # rules are kept apart from the requirement itself

    # Edit: switch questions off; the cut-off goes with it.
    r = again.put(f"/projects/{pid}/tender-rules", json={**body, "questions_allowed": False, "tender_type": "owner_visible"})
    assert r.json()["tender_rules"]["questions_deadline"] is None and r.json()["tender_type"] == "owner_visible"


def test_contradictory_rules_are_refused(db):
    owner = _verified(db, "owner", "owner@example.com")
    pid = _draft(owner)
    put = lambda **kw: owner.put(f"/projects/{pid}/tender-rules", json={"questions_allowed": True, **kw})
    assert put(questions_deadline=(DEADLINE + timedelta(hours=1)).isoformat() + "Z").status_code == 400  # after offers close
    assert put(questions_deadline=(NOW - timedelta(hours=1)).isoformat() + "Z").status_code == 400  # in the past
    assert put(commercial_terms="x" * 5001).status_code == 422
    assert put(questions_deadline=(NOW + timedelta(days=10)).isoformat() + "Z").status_code == 200
    # Pulling the offer deadline in front of the question deadline is refused too.
    assert owner.patch(f"/projects/{pid}", json={"bid_deadline": (NOW + timedelta(days=9)).isoformat() + "Z"}).status_code == 400
    # Rules are fixed once published (amendments are a later stage).
    owner.post(f"/owner/projects/{pid}/publish")
    assert put().status_code == 409


def test_provider_sees_the_rules_the_server_enforces(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "fence@example.com")
    pid = _draft(owner)
    cutoff = NOW + timedelta(days=10)
    owner.put(
        f"/projects/{pid}/tender-rules",
        json={"tender_type": "sealed", "questions_deadline": cutoff.isoformat() + "Z", "commercial_terms": TERMS, "bidder_instructions": INSTRUCTIONS},
    )
    owner.post(f"/owner/projects/{pid}/publish")

    seen = sp.get(f"/projects/{pid}").json()
    rules = seen["tender_rules"]
    assert seen["tender_type"] == "sealed" and seen["bid_deadline"] == DEADLINE.isoformat() + "Z"
    assert rules["questions_open"] is True and rules["questions_close_at"] == cutoff.isoformat() + "Z"
    assert rules["commercial_terms"] == TERMS and rules["bidder_instructions"] == INSTRUCTIONS

    assert sp.post(f"/projects/{pid}/clarifications", json={"question": "Is the gate included?"}).status_code == 201
    # After the question deadline: the page says closed, and the server refuses.
    db.get(Project, pid).questions_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert sp.get(f"/projects/{pid}").json()["tender_rules"]["questions_open"] is False
    r = sp.post(f"/projects/{pid}/clarifications", json={"question": "Height?"})
    assert r.status_code == 400 and "closed" in r.json()["detail"]
    # Offers are still open until the offer deadline: submit, revise, withdraw.
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "3200"}).status_code == 200
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "3150"}).status_code == 200
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert db.query(Offer).count() == 1


def test_questions_switched_off_and_late_questions_are_refused(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "fence@example.com")
    pid = _draft(owner)
    owner.put(f"/projects/{pid}/tender-rules", json={"questions_allowed": False})
    owner.post(f"/owner/projects/{pid}/publish")
    assert sp.get(f"/projects/{pid}").json()["tender_rules"]["questions_open"] is False
    r = sp.post(f"/projects/{pid}/clarifications", json={"question": "Can we visit?"})
    assert r.status_code == 400 and "doesn't accept questions" in r.json()["detail"]

    # Default rule (questions until offers close): a question after the offer
    # deadline is refused even before anything else has noticed the deadline passed.
    other = _draft(owner)
    owner.post(f"/owner/projects/{other}/publish")
    db.get(Project, other).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert sp.post(f"/projects/{other}/clarifications", json={"question": "Late?"}).status_code in (400, 404)

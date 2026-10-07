"""Stage 3.7: the response deadline (when offers must be in -- the one
deadline the tender system enforces) is kept distinct from the expected work
timing (when the owner wants the work done). Both are set on a draft,
persist, and reject obvious contradictions; deadlines travel as explicit UTC."""
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile


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


def _in_days(n: int) -> date:
    return (datetime.utcnow() + timedelta(days=n)).date()


def test_response_deadline_and_work_timing_are_separate_and_persist(db):
    owner = _verified(db, "owner", "owner@example.com")
    # A Kuwait owner picks 17:00 local (UTC+3) on day 14: sent with its offset.
    deadline_local = (datetime.utcnow() + timedelta(days=14)).replace(hour=17, minute=0, second=0, microsecond=0)
    draft = owner.post(
        "/projects", data={"title": "Majlis", "address": "Mishref", "bid_deadline": deadline_local.isoformat() + "+03:00"}
    ).json()
    # Stored and returned as the same instant, explicitly UTC.
    assert draft["bid_deadline"] == deadline_local.replace(hour=14).isoformat() + "Z"
    assert draft["expected_start_date"] is None  # nothing forced

    timing = {"expected_start_date": _in_days(30).isoformat(), "expected_completion_date": _in_days(90).isoformat()}
    assert owner.patch(f"/projects/{draft['id']}", json=timing).status_code == 200

    again = TestClient(app)
    again.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    saved = again.get(f"/projects/{draft['id']}").json()
    assert {k: saved[k] for k in timing} == timing and saved["status"] == "draft"
    assert saved["bid_deadline"].endswith("Z")

    # Switch from a completion date to a duration; clear the start date.
    r = again.patch(f"/projects/{draft['id']}", json={"expected_completion_date": None, "expected_duration_days": 45, "expected_start_date": None})
    assert r.status_code == 200
    assert (r.json()["expected_completion_date"], r.json()["expected_duration_days"], r.json()["expected_start_date"]) == (None, 45, None)

    # The response deadline itself is edited through the same, existing field.
    new_deadline = (datetime.utcnow() + timedelta(days=20)).replace(microsecond=0)
    r = again.patch(f"/projects/{draft['id']}", json={"bid_deadline": new_deadline.isoformat() + "Z"})
    assert r.json()["bid_deadline"] == new_deadline.isoformat() + "Z"


def test_contradictory_dates_are_rejected(db):
    owner = _verified(db, "owner", "owner@example.com")
    deadline = (datetime.utcnow() + timedelta(days=14)).isoformat()
    pid = owner.post("/projects", data={"title": "T", "address": "A", "bid_deadline": deadline}).json()["id"]

    def patch(**body):
        return owner.patch(f"/projects/{pid}", json={k: (v.isoformat() if isinstance(v, date) else v) for k, v in body.items()})

    assert patch(expected_start_date=_in_days(40), expected_completion_date=_in_days(30)).status_code == 400  # ends before it starts
    assert patch(expected_start_date=_in_days(3)).status_code == 400  # starts before offers close
    assert patch(expected_completion_date=_in_days(30), expected_duration_days=10).status_code == 400  # both
    assert patch(expected_duration_days=0).status_code == 400
    # Moving the deadline past an already-set start date is a contradiction too.
    assert patch(expected_start_date=_in_days(20)).status_code == 200
    assert owner.patch(f"/projects/{pid}", json={"bid_deadline": (datetime.utcnow() + timedelta(days=30)).isoformat()}).status_code == 400
    # The creation form path validates the same way.
    r = owner.post("/projects", data={"title": "T", "address": "A", "bid_deadline": deadline, "expected_start_date": _in_days(2).isoformat()})
    assert r.status_code == 400


def test_existing_deadline_enforcement_is_unchanged(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sp@example.com")
    deadline = (datetime.utcnow() + timedelta(days=14)).isoformat()
    project = owner.post(
        "/projects", data={"title": "Live", "address": "A", "bid_deadline": deadline, "status": "open", "expected_duration_days": "30"}
    ).json()
    listing = next(p for p in sp.get("/service-provider/feed").json()["items"] if p["id"] == project["id"])
    assert listing["expected_duration_days"] == 30 and listing["bid_deadline"].endswith("Z")
    assert sp.post(f"/projects/{project['id']}/offers", json={"amount": "1000"}).status_code in (200, 201)

    # Once the authoritative deadline passes, the server refuses offers.
    row = db.get(Project, project["id"])
    row.bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    r = sp.post(f"/projects/{project['id']}/offers", json={"amount": "900"})
    assert r.status_code == 400 and "closed" in r.json()["detail"].lower()

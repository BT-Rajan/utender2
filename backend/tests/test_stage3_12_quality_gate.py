"""Stage 3.12: before a draft can be published, the server checks it is
something a competent Kuwait provider could understand and price. Errors
block publication; warnings advise. A simple service and a detailed
construction requirement aren't held to the same expectations."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project

pytestmark = pytest.mark.quality_gate

DEADLINE = (datetime.utcnow() + timedelta(days=10)).isoformat() + "Z"
AC_SCOPE = "Service 6 split AC units (2-ton): clean filters and coils, check gas pressure, report any faults with a price to fix."


def _owner(db) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": "owner@example.com", "password": "password123", "full_name": "N", "role": "owner"})
    c.put("/account/stakeholder", json={"type": "individual"})
    db.get(OwnerProfile, r.json()["id"]).verification_status = VerificationStatus.approved
    db.commit()
    return c


def _codes(issues):
    return [i["code"] for i in issues]


def test_an_incomplete_draft_is_blocked_with_useful_explanations(db):
    owner = _owner(db)
    pid = owner.post("/projects", data={"title": "Work", "address": "Salwa", "bid_deadline": DEADLINE}).json()["id"]
    q = owner.get(f"/projects/{pid}/quality").json()
    assert q["ready"] is False
    assert set(_codes(q["errors"])) == {"title_too_short", "scope_missing", "governorate_missing"}
    assert {i["section"] for i in q["errors"]} == {"details"}  # where to fix it
    scope = next(i for i in q["errors"] if i["code"] == "scope_missing")
    assert "Describe the work" in scope["message"]

    r = owner.post(f"/owner/projects/{pid}/publish")
    assert r.status_code == 400 and "isn't ready to publish" in r.json()["detail"] and "governorate" in r.json()["detail"]
    assert owner.get(f"/projects/{pid}").json()["status"] == "draft"  # nothing published


def test_a_simple_service_requirement_is_not_held_back(db):
    owner = _owner(db)
    pid = owner.post(
        "/projects",
        data={"title": "AC servicing — villa", "address": "Block 4, Salmiya", "governorate": "hawalli", "area": "Salmiya", "trade": "AC maintenance", "description": AC_SCOPE, "bid_deadline": DEADLINE},
    ).json()["id"]
    q = owner.get(f"/projects/{pid}/quality").json()
    assert q["ready"] is True and q["errors"] == []
    # No false completeness: no drawings, quantities, dates or qualifications expected of it.
    assert not {"documents_missing", "timing_missing", "item_quantity_missing"} & set(_codes(q["warnings"]))
    # The result is "ready for preview": nothing is published until the owner publishes.
    assert owner.get(f"/projects/{pid}").json()["status"] == "draft"
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200


def test_a_detailed_construction_requirement_gets_specific_findings(db):
    owner = _owner(db)
    pid = owner.post(
        "/projects",
        data={
            "title": "Boundary wall — plot 12",
            "address": "Sabah Al-Ahmad, plot 12",
            "governorate": "ahmadi",
            "area": "Sabah Al-Ahmad",
            "description": "Build a 2.4 m block boundary wall with RC columns and a sliding gate, as per the attached drawings.",
            "bid_deadline": DEADLINE,
        },
    ).json()["id"]
    owner.put(
        f"/projects/{pid}/items",
        json={
            "pricing_basis": "per_item",
            "items": [
                {"description": "Excavation", "quantity": "42", "unit": "m³"},
                {"description": "Blockwork 20 cm", "quantity": "180", "unit": None},  # quantity without a unit
                {"description": "Sliding gate", "quantity": None, "unit": None},
            ],
        },
    )
    q = owner.get(f"/projects/{pid}/quality").json()
    assert _codes(q["errors"]) == ["item_unit_missing"] and q["errors"][0]["params"]["position"] == 2
    warnings = set(_codes(q["warnings"]))
    assert {"item_quantity_missing", "timing_missing", "documents_missing"} <= warnings
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 400

    # The owner says providers need the drawings to price it: now a missing
    # drawing blocks publication -- an explicit statement, not a guess from the wording.
    version = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"documents_required": True}, headers={"If-Match": str(version)}).status_code == 200
    q = owner.get(f"/projects/{pid}/quality").json()
    assert "documents_required_missing" in _codes(q["errors"])
    owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("wall-plan.pdf", b"%PDF-1", "application/pdf"))])
    assert "documents_required_missing" not in _codes(owner.get(f"/projects/{pid}/quality").json()["errors"])

    # Priced per item with nothing to price is an error too.
    other = owner.post("/projects", data={"title": "Interlock paving", "address": "Fintas", "governorate": "ahmadi", "description": AC_SCOPE, "bid_deadline": DEADLINE}).json()["id"]
    # Saving that is already refused (Stage 3.4); the gate catches it however it arose.
    assert owner.put(f"/projects/{other}/items", json={"pricing_basis": "per_item", "items": []}).status_code == 400
    db.get(Project, other).pricing_basis = "per_item"
    db.commit()
    assert "per_item_without_items" in _codes(owner.get(f"/projects/{other}/quality").json()["errors"])


def test_contradictory_dates_and_rules_block_publication(db):
    owner = _owner(db)
    pid = owner.post(
        "/projects",
        data={"title": "Kitchen refit", "address": "Mishref", "governorate": "mubarak_al_kabeer", "area": "Mishref", "description": AC_SCOPE, "bid_deadline": DEADLINE},
    ).json()["id"]
    owner.put(f"/projects/{pid}/tender-rules", json={"questions_deadline": (datetime.utcnow() + timedelta(days=5)).isoformat() + "Z"})
    # Data that went stale after it was saved (time passed; a later change).
    row = db.get(Project, pid)
    row.expected_start_date = date.today()  # work starting before offers even close
    row.questions_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    q = owner.get(f"/projects/{pid}/quality").json()
    assert {"timing_contradiction", "questions_deadline_passed"} <= set(_codes(q["errors"]))
    assert {i["section"] for i in q["errors"]} == {"dates", "rules"}
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 400


def test_the_server_decides_whatever_the_page_said(db):
    owner = _owner(db)
    pid = owner.post(
        "/projects",
        data={"title": "AC servicing — villa", "address": "Salmiya", "governorate": "hawalli", "area": "Salmiya", "description": AC_SCOPE, "bid_deadline": DEADLINE},
    ).json()["id"]
    assert owner.get(f"/projects/{pid}/quality").json()["ready"] is True  # what the page last showed
    # The draft then changes (another tab, another member of the organization).
    db.get(Project, pid).governorate = None
    db.commit()
    r = owner.post(f"/owner/projects/{pid}/publish")
    assert r.status_code == 400 and "governorate" in r.json()["detail"]
    # Publishing straight from the start form passes the same gate.
    r = owner.post("/projects", data={"title": "x", "address": "y", "bid_deadline": DEADLINE, "status": "open"})
    assert r.status_code == 400 and db.query(Project).count() == 1
    # Providers' side of the gate: only the owner side can read the report.
    stranger = TestClient(app)
    stranger.post("/auth/signup", json={"email": "s@example.com", "password": "password123", "full_name": "S", "role": "owner"})
    assert stranger.get(f"/projects/{pid}/quality").status_code == 404

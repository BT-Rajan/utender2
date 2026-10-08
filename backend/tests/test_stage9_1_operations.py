"""Stage 9.1: the operator's overview -- the marketplace's state and what
needs attention, from authoritative records: an empty marketplace reads as
empty, not broken; requirements, offers and transactions move between the
right counts; nothing of a sealed offer leaks; a section that fails says so
instead of showing zero; only admins can see any of it."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.project import Project
from app.services import operations
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_15_review_moderation import _admin


def _data(admin, section):
    body = admin.get("/admin/overview").json()
    assert body[section]["available"], section
    return body[section]["data"]


def _kinds(admin):
    return {a["kind"]: a for a in _data(admin, "attention")}


def test_the_overview_follows_the_marketplace(db, monkeypatch):
    admin = _admin(db)
    # A. Empty: every section available, all zero, nothing to attend to, the job's health not yet knowable.
    body = admin.get("/admin/overview").json()
    assert all(body[s]["available"] for s in ("accounts", "requirements", "offers", "transactions", "attention", "background"))
    assert body["requirements"]["data"]["by_status"]["open"] == 0 and body["attention"]["data"] == []
    assert body["background"]["data"] == {"deadline_reminders": "not_determinable", "deadline_reminders_overdue": 0, "email_delivery": "not_configured", "email_failures_24h": 0}

    # Accounts: an organisation of two counts once.
    owner, _colleague, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    providers = [_account(db, "service_provider", f"p{i}@example.com") for i in range(3)]
    accounts = _data(admin, "accounts")
    assert (accounts["owners"]["total"], accounts["owners"]["active"]) == (1, 1)
    assert (accounts["providers"]["total"], accounts["providers"]["can_bid"]) == (3, 3)

    # B. One published requirement, no offers: visible as such.
    r = _tender(owner, title="Tower maintenance", sealed=True)
    req = _data(admin, "requirements")
    assert (req["by_status"]["open"], req["open_without_offers"], req["open_with_offers"]) == (1, 1, 0)
    assert [i["id"] for i in _kinds(admin)["open_without_offers"]["items"]] == [r]

    # C. Three offers on a sealed tender: counted, never opened.
    for p in providers:
        _submitted(p, r)
    offers = _data(admin, "offers")
    assert (offers["by_status"].get("submitted"), offers["on_open_requirements"], offers["submitted_last_7_days"]) == (3, 3, 3)
    assert _data(admin, "requirements")["open_with_offers"] == 1 and "open_without_offers" not in _kinds(admin)
    raw = admin.get("/admin/overview").text
    assert "amount" not in raw and "p0@" not in raw and "message" not in raw

    # D. Awarded: the requirement, the offer and the new transaction agree.
    owner.post(f"/owner/projects/{r}/close")
    db.get(Project, r).bid_deadline = datetime.utcnow() - timedelta(minutes=1)  # a sealed tender closes at its deadline
    db.commit()
    assert "awaiting_owner_decision" in _kinds(admin)
    win = providers[0].get(f"/projects/{r}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{r}/offers/{win}/approve").status_code == 200
    tx = _data(admin, "transactions")
    assert (tx["by_status"]["preparing"], _data(admin, "requirements")["by_status"]["awarded"]) == (1, 1)
    assert [i["id"] for i in _kinds(admin)["agreements_not_in_force"]["items"]] == [r]

    # E. Completed: no longer active or waiting anywhere.
    complete_transaction(owner, providers[0], r)
    tx = _data(admin, "transactions")
    assert (tx["by_status"]["completed"], tx["by_status"]["active"], tx["by_status"]["preparing"], tx["completion_awaiting_owner"]) == (1, 0, 0, 0)
    assert not {"agreements_not_in_force", "completion_awaiting_owner", "awaiting_owner_decision"} & set(_kinds(admin))

    # F. Cancelled and expired requirements are not shown as open.
    c = _tender(owner, title="Cancelled")
    owner.post(f"/owner/projects/{c}/cancel", json={"reason": "other"})
    e = _tender(owner, title="Expiring")
    db.get(Project, e).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    req = _data(admin, "requirements")
    assert (req["by_status"]["open"], req["by_status"]["canceled"], req["by_status"]["expired"] + req["by_status"]["closed"]) == (0, 1, 1)

    # G. A reminder job that isn't running shows; a section that fails says so -- never zero.
    late = _tender(owner, title="Closing soon")
    p = db.get(Project, late)
    p.bid_deadline, p.published_at = datetime.utcnow() + timedelta(hours=12), datetime.utcnow() - timedelta(hours=3)
    db.commit()
    assert _data(admin, "background")["deadline_reminders"] == "overdue"
    assert "open_without_offers_closing_24h" in _kinds(admin)

    def broken(db, now):
        raise RuntimeError("database gone")

    monkeypatch.setattr(operations, "SECTIONS", tuple((n, broken if n == "offers" else f) for n, f in operations.SECTIONS))
    body = admin.get("/admin/overview").json()
    assert body["offers"] == {"available": False, "data": None} and body["requirements"]["available"]

    # Only admins.
    assert owner.get("/admin/overview").status_code == 403
    assert providers[0].get("/admin/overview").status_code == 403
    assert TestClient(app).get("/admin/overview").status_code == 401

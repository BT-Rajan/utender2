"""Stage 3.16: a published requirement can end without a U-Tender award in
ways that mean different things -- canceled, expired, closed outside
U-Tender, no suitable offer -- each kept distinguishable, none pretending an
award happened, none erasing what providers submitted, and none reopened by
an ordinary edit."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import VerificationStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project
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


def _published(owner: TestClient, tender_type: str = "owner_visible") -> str:
    return owner.post(
        "/projects",
        data={"title": "Majlis extension", "address": "Mishref", "governorate": "mubarak_al_kabeer", "description": "Extend the majlis by 4 m.", "bid_deadline": _when(10), "status": "open", "tender_type": tender_type},
    ).json()["id"]


def _no_award_recorded(db, pid) -> bool:
    return db.query(AwardRecord).filter(AwardRecord.project_id == pid).count() == 0 and all(o.status.value != "approved" for o in db.query(Offer).filter_by(project_id=pid))


def test_cancel(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    beta = _verified(db, "service_provider", "beta@example.com")
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "3000", "message": "Our quotation."})
    assert owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "unknown"}).status_code == 400
    r = owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "postponed", "note": "Bank financing delayed."})
    assert r.status_code == 200 and (r.json()["status"], r.json()["closure_reason"]) == ("canceled", "postponed") and r.json()["closed_at"]
    # No new offers; not an open opportunity; the existing offer and its history stay.
    assert beta.post(f"/projects/{pid}/offers", json={"amount": "2000"}).status_code == 400
    assert all(p["id"] != pid for p in beta.get("/service-provider/feed").json())
    mine = alpha.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["amount"], mine["message"], mine["status"]) == ("3000.000", "Our quotation.", "submitted")
    # The bidder sees it was canceled -- but not the owner's private note.
    seen = alpha.get(f"/projects/{pid}").json()
    assert (seen["status"], seen["closure_reason"]) == ("canceled", "postponed") and "Bank" not in str(seen)
    assert db.query(Notification).filter(Notification.type == "tender_cancelled").count() == 1
    entry = db.query(AuditLog).filter(AuditLog.action == "project.cancel").one()
    assert entry.reason == "Bank financing delayed." and entry.new_value == "canceled:postponed"
    assert _no_award_recorded(db, pid)


def test_deadline_passes(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    with_offer, without = _published(owner), _published(owner)
    alpha.post(f"/projects/{with_offer}/offers", json={"amount": "3000"})
    for pid in (with_offer, without):
        db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert alpha.post(f"/projects/{with_offer}/offers", json={"amount": "2900"}).status_code == 400
    a, b = owner.get(f"/projects/{with_offer}").json(), owner.get(f"/projects/{without}").json()
    assert (a["status"], b["status"]) == ("closed", "expired")  # waiting on the owner / nothing to decide
    assert a["closed_at"] and alpha.get(f"/projects/{with_offer}").json()["status"] == "closed"
    assert str(db.query(Offer).one().amount) == "3000.000" and _no_award_recorded(db, with_offer)


def test_closed_outside_u_tender(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "3000"})
    r = owner.post(f"/owner/projects/{pid}/close-externally", json={"note": "Using my cousin's contractor."})
    assert r.status_code == 200 and (r.json()["status"], r.json()["closure_reason"]) == ("no_award", "closed_externally")
    assert _no_award_recorded(db, pid)  # no U-Tender award pretended
    assert alpha.post(f"/projects/{pid}/offers", json={"amount": "2500"}).status_code == 400
    assert db.query(Offer).one().status.value == "submitted"
    assert alpha.get(f"/projects/{pid}").json()["closure_reason"] == "closed_externally"
    # It can't then be awarded on U-Tender after all.
    oid = db.query(Offer).one().id
    assert owner.post(f"/owner/projects/{pid}/offers/{oid}/approve").status_code == 400

    # A sealed tender closed outside U-Tender early: its bids stay sealed until the deadline.
    sealed = _published(owner, "sealed")
    alpha.post(f"/projects/{sealed}/offers", json={"amount": "2800"})
    owner.post(f"/owner/projects/{sealed}/close-externally")
    seen = owner.get(f"/owner/projects/{sealed}/offers").json()[0]
    assert seen["sealed"] is True and seen["amount"] is None


def test_none_of_the_offers_is_suitable(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "9999"})
    assert owner.post(f"/owner/projects/{pid}/no-award").status_code == 400  # offers still open: close first
    owner.post(f"/owner/projects/{pid}/close")
    r = owner.post(f"/owner/projects/{pid}/no-award", json={"note": "All far above budget."})
    assert (r.json()["status"], r.json()["closure_reason"]) == ("no_award", "no_suitable_offer")
    assert _no_award_recorded(db, pid) and db.query(Offer).one().status.value == "submitted"


def test_terminal_outcomes_stay_terminal(db):
    owner = _verified(db, "owner", "owner@example.com")
    pids = {}
    pids["canceled"] = _published(owner)
    owner.post(f"/owner/projects/{pids['canceled']}/cancel", json={"reason": "not_needed"})
    pids["external"] = _published(owner)
    owner.post(f"/owner/projects/{pids['external']}/close-externally")
    pids["expired"] = _published(owner)
    db.get(Project, pids["expired"]).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.get(f"/projects/{pids['expired']}")
    for name, pid in pids.items():
        status = owner.get(f"/projects/{pid}").json()["status"]
        assert owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(20)}).status_code == 400, name
        assert owner.patch(f"/projects/{pid}", json={"title": "Reopened?"}).status_code == 400, name
        for action in ("publish", "resume", "close", "cancel", "close-externally"):
            assert owner.post(f"/owner/projects/{pid}/{action}").status_code == 400, (name, action)
        assert owner.post(f"/owner/projects/{pid}/pause", json={"reason": "again"}).status_code == 400, name
        assert owner.get(f"/projects/{pid}").json()["status"] == status, name


def test_only_the_owner_side_ends_a_requirement(db):
    owner = _verified(db, "owner", "owner@example.com")
    other = _verified(db, "owner", "other@example.com")
    sp = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    for client, expected in ((sp, 403), (other, 404)):
        for action in ("cancel", "close-externally", "no-award"):
            assert client.post(f"/owner/projects/{pid}/{action}").status_code == expected, action
    assert db.get(Project, pid).status.value == "open"


def test_the_owner_side_reads_its_private_note(db):
    owner = _verified(db, "owner", "owner@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    alpha.post(f"/projects/{pid}/offers", json={"amount": "3000"})
    r = owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "postponed", "note": "Bank financing delayed."})
    assert r.json()["closure_note"] == "Bank financing delayed."
    assert owner.get(f"/projects/{pid}").json()["closure_note"] == "Bank financing delayed."
    assert next(p for p in owner.get("/owner/projects").json() if p["id"] == pid)["closure_note"] == "Bank financing delayed."
    seen = alpha.get(f"/projects/{pid}").json()
    assert seen["closure_note"] is None and "Bank" not in str(seen) and "Bank" not in str(alpha.get("/service-provider/my-bids").json())


def test_an_ended_requirement_can_be_started_again_as_a_new_draft(db):
    owner = _verified(db, "owner", "owner@example.com")
    other = _verified(db, "owner", "other@example.com")
    alpha = _verified(db, "service_provider", "alpha@example.com")
    pid = _published(owner)
    owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("plan.pdf", b"%PDF-plan", "application/pdf"))])
    alpha.post(f"/projects/{pid}/offers", json={"amount": "3000"})
    assert owner.post(f"/owner/projects/{pid}/restart").status_code == 400  # still open: nothing to restart
    owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "postponed"})
    assert other.post(f"/owner/projects/{pid}/restart").status_code == 404
    assert alpha.post(f"/owner/projects/{pid}/restart").status_code == 403

    r = owner.post(f"/owner/projects/{pid}/restart", json={"creation_token": "again-1"})
    assert r.status_code == 201
    new = r.json()
    assert new["id"] != pid and new["status"] == "draft" and new["closure_reason"] is None and new["offer_count"] == 0
    assert new["restarted_from_id"] == pid and owner.get(f"/projects/{new['id']}").json()["restarted_from_id"] == pid
    assert owner.post(f"/owner/projects/{pid}/restart", json={"creation_token": "again-1"}).json()["id"] == new["id"]  # a retry: same draft
    draft = owner.get(f"/projects/{new['id']}").json()
    assert (draft["title"], draft["description"]) == ("Majlis extension", "Extend the majlis by 4 m.")
    doc = draft["drawings"][0]
    assert doc["file_name"] == "plan.pdf" and owner.get("/" + doc["url"].split("://", 1)[-1].split("/", 1)[-1]).content == b"%PDF-plan"
    # The old one is untouched: still canceled, its offer still there; nobody else sees the draft.
    old = owner.get(f"/projects/{pid}").json()
    assert (old["status"], old["closure_reason"], old["offer_count"]) == ("canceled", "postponed", 1)
    assert alpha.get(f"/projects/{new['id']}").status_code == 404
    assert db.query(AuditLog).filter(AuditLog.action == "project.restart", AuditLog.previous_value == pid).count() == 1


def test_providers_who_were_told_hear_it_ended(db, monkeypatch):
    from app.models.clarification import Clarification
    from app.services import email as email_service

    sent = []
    monkeypatch.setattr(email_service, "_send", lambda to, subject, html: sent.append((to, subject)))

    owner = _verified(db, "owner", "owner@example.com")
    bidder = _verified(db, "service_provider", "alpha@example.com")
    asker = _verified(db, "service_provider", "beta@example.com")
    told = _verified(db, "service_provider", "gamma@example.com")
    _verified(db, "service_provider", "delta@example.com")  # never told about it
    pid = _published(owner)
    told_id = told.get("/auth/me").json()["id"]
    db.add(Notification(user_id=told_id, type="new_requirement", title="New", body="x", link=f"/service-provider/projects/{pid}/offer"))
    db.commit()
    bidder.post(f"/projects/{pid}/offers", json={"amount": "3000"})
    assert asker.post(f"/projects/{pid}/clarifications", json={"question": "Is parking available?"}).status_code in (200, 201)
    assert db.query(Clarification).count() == 1

    owner.post(f"/owner/projects/{pid}/close-externally")
    ended = {db.get(ServiceProviderProfile, n.user_id).company_name for n in db.query(Notification).filter(Notification.type == "requirement_ended")}
    assert ended == {"beta", "gamma"}  # the bidder gets its own notice instead
    assert {to for to, subject in sent if subject.startswith("Requirement ended")} == {"beta@example.com", "gamma@example.com"}
    assert db.query(Notification).filter(Notification.type == "tender_no_award").count() == 1
    assert db.query(Notification).filter(Notification.type == "new_requirement", Notification.is_read.is_(False)).count() == 0

"""Stage 5.2: Participate starts the provider's one offer on a requirement as
a draft -- the same offers row a submission later completes. It belongs to
the requirement, its version and the provider's stakeholder; persists across
visits; is private to the provider's side; is never seen, counted or treated
as an offer by anyone else; and only ever becomes an offer by being
submitted while bidding is open."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import NotificationType, OfferStatus, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer, OfferRevision
from app.models.project import Project
from app.services.team import org_of
from tests.test_stage4_9_participation import _account, _admin, _publish, _when

needs_mysql = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs real row locking (MySQL)")


def _member(db, boss, email):
    c = _account(db, "service_provider", email, joining=True)
    token = boss.post("/account/organization/invitations", json={"email": email}).json()["link"].rsplit("/", 1)[-1]
    c.post(f"/account/invitations/{token}/accept")
    return c


def _login(email):
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def test_participate_starts_one_persistent_draft(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    me = sp.get("/auth/me").json()["id"]
    assert sp.get(f"/projects/{pid}/offers/mine").json() is None
    # Double-click, a second tab, a retry: one draft, the same identity each time.
    ids = {sp.post(f"/projects/{pid}/participate").json()["offer_id"] for _ in range(3)}
    assert len(ids) == 1 and None not in ids
    offer_id = ids.pop()
    draft = db.query(Offer).one()
    assert (draft.id, draft.project_id, draft.service_provider_id, draft.organization_id) == (offer_id, pid, me, None)
    assert (draft.status, draft.amount, draft.created_by, draft.updated_by) == (OfferStatus.draft, None, me, me)
    assert draft.based_on_material_revision == db.get(Project, pid).material_revision
    # Refresh, leave and come back, log out and in: the same draft, still unsubmitted.
    sp.post("/auth/logout")
    again = _login("noor@example.com")
    mine = again.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["id"], mine["status"], mine["amount"]) == (offer_id, "draft", None)
    verdict = again.get(f"/projects/{pid}").json()["participation"]
    assert (verdict["started"], verdict["offer_id"], verdict["offer_status"]) == (True, offer_id, "draft")
    assert again.get(f"/projects/{pid}/offers/mine/history").json() == []
    # Participating doesn't lock the tender type: nothing has been offered.
    assert db.get(Project, pid).tender_type_locked is False


def test_a_draft_is_nobody_elses_business(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com", organization="Rival Co")
    admin = _admin(db)
    pid = _publish(owner)
    offer_id = sp.post(f"/projects/{pid}/participate").json()["offer_id"]
    # The owner: no offer, no count, no history, nothing to award.
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    assert owner.get(f"/projects/{pid}").json()["offer_count"] == 0
    assert all(p["offer_count"] == 0 for p in owner.get("/owner/projects").json() if p["id"] == pid)
    assert owner.get(f"/owner/projects/{pid}/offers/{offer_id}/history").status_code == 404
    # A competitor: their own (none), and a count that doesn't include it.
    assert rival.get(f"/projects/{pid}/offers/mine").json() is None
    assert rival.get(f"/projects/{pid}").json()["participation"]["offer_id"] is None
    assert next(p for p in rival.get("/service-provider/feed").json()["items"] if p["id"] == pid)["offer_count"] == 0
    # Admin lists and moderation: not an offer yet.
    assert all(o["id"] != offer_id for o in admin.get("/admin/offers").json())
    assert admin.get(f"/admin/projects/{pid}").json()["offers"] == []
    assert next(p for p in admin.get("/admin/projects").json() if p["id"] == pid)["offer_count"] == 0
    assert admin.patch(f"/admin/offers/{offer_id}", json={"amount": "1"}).status_code == 404
    assert admin.post(f"/admin/offers/{offer_id}/suspend", json={"suspended": True, "reason": "x"}).status_code == 404
    # Not among the provider's bids; nothing to withdraw or confirm.
    assert sp.get("/service-provider/my-bids").json() == []
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 404
    assert sp.post(f"/projects/{pid}/offers/confirm").status_code == 404
    assert db.query(Offer).one().status == OfferStatus.draft


def test_manipulated_ids_reach_nothing(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com", organization="Rival Co")
    pid, other = _publish(owner, "Villa"), _publish(owner, "Warehouse")
    rival_id = rival.get("/auth/me").json()["id"]
    sp_draft = sp.post(f"/projects/{pid}/participate", json={"service_provider_id": rival_id, "organization_id": "x", "offer_id": "y"}).json()["offer_id"]
    rival_draft = rival.post(f"/projects/{pid}/participate").json()["offer_id"]
    assert sp_draft != rival_draft and db.query(Offer).count() == 2
    assert db.get(Offer, sp_draft).service_provider_id == sp.get("/auth/me").json()["id"] and db.get(Offer, sp_draft).organization_id is None
    assert db.get(Offer, rival_draft).organization_id == org_of(db, rival_id)
    # Each side sees only its own, whatever is put in the query.
    assert sp.get(f"/projects/{pid}/offers/mine", params={"offer_id": rival_draft, "service_provider_id": rival_id}).json()["id"] == sp_draft
    assert rival.get(f"/projects/{pid}/offers/mine").json()["id"] == rival_draft
    # Another requirement: not this draft.
    assert sp.get(f"/projects/{other}/offers/mine").json() is None
    # Another provider's draft id in owner/admin routes: refused (wrong role).
    assert sp.get(f"/owner/projects/{pid}/offers/{rival_draft}/history").status_code == 403
    assert sp.patch(f"/admin/offers/{rival_draft}", json={"amount": "1"}).status_code == 403


def test_an_organization_shares_one_draft(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _member(db, boss, "eng@gulf.example")
    ops = _member(db, boss, "ops@gulf.example")
    pid = _publish(owner)
    started = eng.post(f"/projects/{pid}/participate").json()["offer_id"]
    assert {c.post(f"/projects/{pid}/participate").json()["offer_id"] for c in (ops, boss, eng)} == {started}
    assert {c.get(f"/projects/{pid}/offers/mine").json()["id"] for c in (boss, eng, ops)} == {started}
    draft = db.query(Offer).one()
    boss_id = boss.get("/auth/me").json()["id"]
    assert (draft.service_provider_id, draft.organization_id) == (boss_id, org_of(db, boss_id))
    assert draft.created_by == eng.get("/auth/me").json()["id"]
    # Submitting completes the same row: the organization's one offer.
    assert ops.post(f"/projects/{pid}/offers", json={"amount": "900"}).json()["id"] == started
    offer = db.query(Offer).one()
    db.refresh(offer)
    assert offer.status == OfferStatus.submitted and offer.revision == 1 and db.query(OfferRevision).count() == 0
    assert (offer.created_by, offer.updated_by) == (eng.get("/auth/me").json()["id"], ops.get("/auth/me").json()["id"])
    assert db.get(Project, pid).tender_type_locked is True
    # Participating again leaves the submitted offer as it is.
    assert boss.post(f"/projects/{pid}/participate").json()["offer_status"] == "submitted"


def test_the_draft_follows_the_requirement_and_never_becomes_an_offer_by_itself(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    extended, amended, expiring, canceled, suspended = (_publish(owner, t) for t in ("Extended", "Amended", "Expiring", "Canceled", "Suspended"))
    drafts = {pid: sp.post(f"/projects/{pid}/participate").json()["offer_id"] for pid in (extended, amended, expiring, canceled, suspended)}

    # Extended: the same draft on the same requirement.
    v = owner.get(f"/projects/{extended}").json()["version"]
    assert owner.patch(f"/projects/{extended}", json={"bid_deadline": _when(20)}, headers={"If-Match": str(v)}).status_code == 200
    assert sp.get(f"/projects/{extended}/offers/mine").json()["id"] == drafts[extended]

    # Amended: the draft keeps the version it was started on until the provider
    # has seen the current one; they're told as someone preparing an offer.
    v = owner.get(f"/projects/{amended}").json()["version"]
    owner.patch(f"/projects/{amended}", json={"description": "Rewire a villa: 40 points plus 6 outdoor."}, headers={"If-Match": str(v)})
    assert db.get(Offer, drafts[amended]).based_on_material_revision == 0 and db.get(Project, amended).material_revision == 1
    sp_id = sp.get("/auth/me").json()["id"]
    assert db.query(Notification).filter(Notification.user_id == sp_id, Notification.type == NotificationType.tender_amendment).count() == 1
    assert sp.post(f"/projects/{amended}/participate").json()["offer_id"] == drafts[amended]
    db.expire_all()
    assert db.get(Offer, drafts[amended]).based_on_material_revision == 1

    # Deadline passes with only a draft: nothing was offered, so it expires (not closed for evaluation).
    db.get(Project, expiring).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.post(f"/owner/projects/{canceled}/cancel", json={"reason": "not_needed"})
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})
    sp.get("/service-provider/feed")  # any read syncs the deadline
    db.expire_all()
    assert db.get(Project, expiring).status == ProjectStatus.expired
    for pid in (expiring, canceled, suspended):
        # Preserved, still a draft, and it can't be submitted now.
        assert db.get(Offer, drafts[pid]).status == OfferStatus.draft
        assert sp.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 400
        assert sp.post(f"/projects/{pid}/participate").status_code == 400
        assert db.get(Offer, drafts[pid]).status == OfferStatus.draft
    # Suspension lifted: the same draft is still there to continue.
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": False})
    assert sp.post(f"/projects/{suspended}/participate").json()["offer_id"] == drafts[suspended]
    assert db.query(Offer).count() == 5 and sp.get("/service-provider/my-bids").json() == []


@needs_mysql
def test_simultaneous_starts_make_one_draft(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _member(db, boss, "eng@gulf.example")
    pid = _publish(owner)
    clients = [boss, eng, _login("boss@gulf.example"), _login("eng@gulf.example")]
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: c.post(f"/projects/{pid}/participate"), clients))
    assert all(r.status_code == 200 for r in results)
    db.expire_all()
    assert db.query(Offer).count() == 1
    assert {c.get(f"/projects/{pid}/offers/mine").json()["id"] for c in clients} == {db.query(Offer).one().id}

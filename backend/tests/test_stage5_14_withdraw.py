"""Stage 5.14: withdrawing a submitted offer -- the existing rule (withdraw
while offers are open, before the deadline), judged by the server under the
requirement's lock: the provider's own offer only, kept (not deleted) with
its documents and history, no longer a live offer, sealed rules intact,
once only, and resubmittable as before."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import OfferStatus, ProjectStatus
from app.models.offer import Offer, OfferDocument, OfferRevision
from app.models.project import Project
from app.services.storage import get_storage
from tests.test_stage4_9_participation import _account, _admin, _when

needs_mysql = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs real row locking (MySQL)")
DECL = "I have visited the site."
W = "/projects/{}/offers/withdraw"


def _tender(owner, title="HV works", sealed=False, days=10):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Substation.", "bid_deadline": _when(days),
                                       "tender_type": "sealed" if sealed else "owner_visible"}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"documents": [{"name": "Method statement", "required": True}], "declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _submitted(sp, pid, amount="1000"):
    sp.post(f"/projects/{pid}/participate")
    sp.put(f"/projects/{pid}/offers/draft", json={"amount": amount, "message": "Method", "accepted_declarations": [DECL]})
    sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("m.pdf", b"%PDF-m", "application/pdf")})
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code == 200, r.text
    return r.json()


def test_withdraw_keeps_everything_and_stops_it_being_live(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    offer = _submitted(sp, pid)
    r = sp.post(W.format(pid))
    assert r.status_code == 200, r.text
    w = r.json()
    # The same offer, now withdrawn; its content and documents kept; the submitted version on record.
    assert (w["id"], w["status"], w["revision"], w["amount"], w["message"]) == (offer["id"], "withdrawn", 2, "1000.000", "Method")
    assert [d["file_name"] for d in w["documents"]] == ["m.pdf"]
    assert db.query(Offer).count() == 1 and db.query(OfferDocument).count() == 1
    hist = db.query(OfferRevision).one()
    assert (hist.revision_number, hist.status, hist.submitted_at is not None) == (1, OfferStatus.submitted, True)
    assert get_storage().download("offer-documents", db.query(OfferDocument).one().file_path) == b"%PDF-m"
    # Shown as withdrawn everywhere, on refresh too.
    assert sp.get(f"/projects/{pid}/offers/mine").json()["status"] == "withdrawn"
    assert [b["offer_status"] for b in sp.get("/service-provider/my-bids").json()] == ["withdrawn"]
    assert [o["status"] for o in owner.get(f"/owner/projects/{pid}/offers").json()] == ["withdrawn"]
    # Once only: a double-click, a second tab or a retry changes nothing more.
    for _ in range(2):
        again = sp.post(W.format(pid))
        assert again.status_code == 400 and "already been withdrawn" in again.json()["detail"]
    assert db.query(OfferRevision).count() == 1
    # No longer a live offer: at the deadline, the requirement expires (nothing to evaluate) ...
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    sp.get("/service-provider/feed")
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.expired


def test_cannot_be_awarded_and_resubmission_works_as_before(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    other = _account(db, "service_provider", "other@example.com")
    pid = _tender(owner)
    offer = _submitted(sp, pid)
    _submitted(other, pid, "2000")
    sp.post(W.format(pid))
    # Resubmission under the existing rule: the same offer, submitted again, the withdrawal on record.
    again = sp.post(f"/projects/{pid}/offers", json={"amount": "950", "message": "Method", "accepted_declarations": [DECL]}, headers={"If-Match": "2"})
    assert again.status_code == 200 and (again.json()["id"], again.json()["status"], again.json()["revision"]) == (offer["id"], "submitted", 3)
    assert [h["status"] for h in sp.get(f"/projects/{pid}/offers/mine/history").json()] == ["submitted", "withdrawn"]
    # Withdrawn again, then the deadline passes: the withdrawn offer can't be awarded; the live one can.
    sp.post(W.format(pid))
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    sp.get("/service-provider/feed")
    assert owner.post(f"/owner/projects/{pid}/offers/{offer['id']}/approve").status_code == 400
    live = db.query(Offer).filter(Offer.status == OfferStatus.submitted).one()
    assert owner.post(f"/owner/projects/{pid}/offers/{live.id}/approve").status_code == 200
    # After the award, nothing can be withdrawn or changed.
    assert other.post(W.format(pid)).status_code == 400


def test_only_while_offers_are_open_and_only_ones_own(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com", organization="Rival Co")
    admin = _admin(db)
    states = ("at", "after", "closed_early", "canceled", "suspended", "paused")
    pids = {s: _tender(owner, s) for s in states}
    for pid in pids.values():
        _submitted(sp, pid)
    db.get(Project, pids["at"]).bid_deadline = datetime.utcnow().replace(microsecond=0)  # exactly at the deadline (whole seconds, as stored)
    db.get(Project, pids["after"]).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner.post(f"/owner/projects/{pids['closed_early']}/close")
    owner.post(f"/owner/projects/{pids['canceled']}/cancel", json={"reason": "not_needed"})
    admin.post(f"/admin/projects/{pids['suspended']}/suspend", json={"suspended": True})
    owner.post(f"/owner/projects/{pids['paused']}/pause", json={"reason": "Permit."})
    for state, pid in pids.items():
        assert sp.post(W.format(pid)).status_code == 400, state
        assert db.query(Offer).filter(Offer.project_id == pid).one().status == OfferStatus.submitted, state
    # Someone else's offer: another provider (with its ids in the request), the owner, a draft.
    pid = _tender(owner, "Open")
    mine = _submitted(sp, pid)
    r = rival.post(W.format(pid), json={"offer_id": mine["id"]}, params={"offer_id": mine["id"], "service_provider_id": mine["service_provider_id"]})
    assert r.status_code == 404
    assert owner.post(W.format(pid)).status_code == 403
    rival.post(f"/projects/{pid}/participate")  # only a draft
    assert rival.post(W.format(pid)).status_code == 404
    assert db.query(Offer).filter(Offer.id == mine["id"]).one().status == OfferStatus.submitted


def test_sealed_withdrawal_reveals_nothing(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner, sealed=True)
    _submitted(sp, pid, "98765.432")
    sp.post(W.format(pid))
    listed = owner.get(f"/owner/projects/{pid}/offers").json()
    assert [o["status"] for o in listed] == ["withdrawn"] and listed[0]["amount"] is None and listed[0]["service_provider_id"] is None
    assert "98765" not in str(listed) and owner.get(f"/owner/projects/{pid}/offers/{listed[0]['id']}/history").status_code == 404


@needs_mysql
def test_withdraw_racing_the_owners_close_has_one_outcome(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    with ThreadPoolExecutor(2) as pool:
        w = pool.submit(lambda: sp.post(W.format(pid)))
        c = pool.submit(lambda: owner.post(f"/owner/projects/{pid}/close"))
        w, c = w.result(), c.result()
    db.expire_all()
    offer, project = db.query(Offer).one(), db.get(Project, pid)
    if w.status_code == 200:  # withdrawn first: closed with no live offer
        assert offer.status == OfferStatus.withdrawn
    else:  # closed first: the offer stays submitted, under evaluation-ready closed state
        assert offer.status == OfferStatus.submitted and project.status == ProjectStatus.closed


@needs_mysql
def test_simultaneous_withdrawals_record_once(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    clients = [sp]
    for _ in range(3):
        c = TestClient(app)
        c.post("/auth/login", json={"email": "noor@example.com", "password": "password123"})
        clients.append(c)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: c.post(W.format(pid)), clients))
    assert sorted(r.status_code for r in results) == [200, 400, 400, 400]
    db.expire_all()
    assert db.query(OfferRevision).count() == 1 and db.query(Offer).one().status == OfferStatus.withdrawn

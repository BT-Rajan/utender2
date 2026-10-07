"""Stage 5.15: deadline, concurrency and submission integrity across every
route that changes a provider's offer. Every one is judged by the server's
clock under the requirement's lock, against the requirement's lifecycle as
it is at that moment, so each request ends in one valid state."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import OfferStatus, ProjectStatus
from app.models.offer import Offer, OfferRevision
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _when

needs_mysql = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs real row locking (MySQL)")
DECL = "I have visited the site."


def _d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _tender(owner, title="HV works"):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Substation.", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _draft(sp, pid, **extra):
    sp.post(f"/projects/{pid}/participate")
    assert sp.put(f"/projects/{pid}/offers/draft", json={"amount": "1000", "message": "Method", "accepted_declarations": [DECL], **extra}).status_code == 200


def _submitted(sp, pid, **extra):
    _draft(sp, pid, **extra)
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code == 200, r.text
    return r.json()


# Every provider route that changes an offer (or starts one), as the server sees it.
def _draft_changes(pid):
    return [
        ("participate", "post", f"/projects/{pid}/participate", {}),
        ("save draft", "put", f"/projects/{pid}/offers/draft", {"json": {"amount": "1"}}),
        ("save price", "put", f"/projects/{pid}/offers/draft/commercial", {"json": {"amount": "1"}}),
        ("attach document", "post", f"/projects/{pid}/offers/documents", {"data": {"label": "x"}, "files": {"file": ("a.pdf", b"%PDF", "application/pdf")}}),
        ("submit draft", "post", f"/projects/{pid}/offers/draft/submit", {}),
    ]


def _offer_changes(pid):
    return [
        ("revise", "post", f"/projects/{pid}/offers", {"json": {"amount": "900", "message": "M", "accepted_declarations": [DECL]}}),
        ("withdraw", "post", f"/projects/{pid}/offers/withdraw", {}),
    ]


def test_the_deadline_is_the_servers_at_every_route(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    drafting, offered = _tender(owner, "Drafting"), _tender(owner, "Offered")
    _draft(sp, drafting)
    _submitted(sp, offered)
    # Exactly at the deadline (whole seconds, as stored): every change is refused, whatever the client claims.
    for pid in (drafting, offered):
        db.get(Project, pid).bid_deadline = datetime.utcnow().replace(microsecond=0)
    db.commit()
    fake = {"Date": (datetime.utcnow() - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S GMT"), "X-Client-Time": "2000-01-01T00:00:00Z"}
    for name, method, url, kw in _draft_changes(drafting) + _offer_changes(offered):
        r = getattr(sp, method)(url, headers=fake, **kw)
        assert r.status_code == 400, (name, r.status_code, r.text)
    # Nothing changed: the draft is a draft, the offer is as submitted.
    assert db.query(Offer).filter(Offer.project_id == drafting).one().status == OfferStatus.draft
    o = db.query(Offer).filter(Offer.project_id == offered).one()
    db.refresh(o)
    assert (o.status, o.revision, o.amount) == (OfferStatus.submitted, 1, 1000)
    # The read that follows moves the requirement on (closed: a live offer; expired: none).
    sp.get("/service-provider/feed")
    db.expire_all()
    assert (db.get(Project, offered).status, db.get(Project, drafting).status) == (ProjectStatus.closed, ProjectStatus.expired)


def test_every_lifecycle_state_blocks_every_change(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    pids = {s: (_tender(owner, s + "-d"), _tender(owner, s + "-o")) for s in ("suspended", "paused", "canceled", "closed_early")}
    for drafting, offered in pids.values():
        _draft(sp, drafting)
        _submitted(sp, offered)
    for state, (drafting, offered) in pids.items():
        for pid in (drafting, offered):
            if state == "suspended":
                admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True})
            elif state == "paused":
                owner.post(f"/owner/projects/{pid}/pause", json={"reason": "Permit."})
            elif state == "canceled":
                owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "not_needed"})
            else:
                owner.post(f"/owner/projects/{pid}/close")
        for name, method, url, kw in _draft_changes(drafting) + _offer_changes(offered):
            assert getattr(sp, method)(url, **kw).status_code == 400, (state, name)
    assert all(o.status in (OfferStatus.draft, OfferStatus.submitted) and o.revision == 1 for o in db.query(Offer))


def test_confirming_after_an_amendment_rechecks_the_commitment(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    _submitted(sp, pid, proposed_start_date=_d(12), proposed_duration_days=10)
    # The owner extends the deadline past the committed start, with a material change.
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(20), "description": "Substation, plus a second bay."}, headers={"If-Match": str(v)}).status_code == 200
    # "Confirm it still stands" is refused: as submitted it now starts before offers close.
    r = sp.post(f"/projects/{pid}/offers/confirm")
    assert r.status_code == 400 and "before the response deadline" in r.json()["detail"]
    o = db.query(Offer).one()
    db.refresh(o)
    assert (o.based_on_material_revision, o.revision) == (0, 1)  # still on record against the old version, unchanged
    # Revising with a valid commitment works, against the current version.
    r = sp.post(f"/projects/{pid}/offers", json={"amount": "1000", "message": "Method", "accepted_declarations": [DECL], "proposed_start_date": _d(25), "proposed_duration_days": 10},
                headers={"If-Match": "1"})
    assert r.status_code == 200 and r.json()["based_on_material_revision"] == 1


def test_retries_and_refreshes_show_one_persisted_outcome(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    first = _submitted(sp, pid)
    # A retried submit, an old tab's revision, a double withdraw: one state, on record.
    assert sp.post(f"/projects/{pid}/offers/draft/submit").status_code == 409
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "900", "message": "M", "accepted_declarations": [DECL]}, headers={"If-Match": "0"}).status_code == 409
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    # A revision made from the page that showed the submitted offer (revision 1) is now stale: refused.
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "900", "message": "M", "accepted_declarations": [DECL]}, headers={"If-Match": "1"}).status_code == 409
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["id"], mine["status"], mine["revision"]) == (first["id"], "withdrawn", 2)
    assert db.query(Offer).count() == 1 and db.query(OfferRevision).count() == 1


@needs_mysql
def test_races_end_in_one_valid_state(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    # A revision and a withdrawal at once (two tabs): one is applied, the other judged against it.
    pid = _tender(owner, "Revise vs withdraw")
    _submitted(sp, pid)
    tab = TestClient(app)
    tab.post("/auth/login", json={"email": "noor@example.com", "password": "password123"})
    with ThreadPoolExecutor(2) as pool:
        rev = pool.submit(lambda: sp.post(f"/projects/{pid}/offers", json={"amount": "900", "message": "M", "accepted_declarations": [DECL]}, headers={"If-Match": "1"}))
        wd = pool.submit(lambda: tab.post(f"/projects/{pid}/offers/withdraw"))
        rev, wd = rev.result(), wd.result()
    db.expire_all()
    o = db.query(Offer).filter(Offer.project_id == pid).one()
    assert wd.status_code == 200 and o.status == OfferStatus.withdrawn  # withdraw always applies to the offer as it then is
    assert (rev.status_code, o.revision) in ((200, 3), (409, 2))  # revised first then withdrawn, or refused as stale
    # A submission and an admin suspension at once: accepted before it, or refused after it -- never both.
    pid = _tender(owner, "Submit vs suspend")
    _draft(sp, pid)
    with ThreadPoolExecutor(2) as pool:
        sub = pool.submit(lambda: sp.post(f"/projects/{pid}/offers/draft/submit"))
        sus = pool.submit(lambda: admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True}))
        sub, sus = sub.result(), sus.result()
    db.expire_all()
    o, p = db.query(Offer).filter(Offer.project_id == pid).one(), db.get(Project, pid)
    assert p.is_suspended and ((sub.status_code == 200 and o.status == OfferStatus.submitted) or (sub.status_code == 400 and o.status == OfferStatus.draft))
    # An award and an admin suspension of the winning offer at once: never an awarded offer that is suspended.
    pid = _tender(owner, "Award vs suspend")
    winner = _submitted(sp, pid)
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    sp.get("/service-provider/feed")
    with ThreadPoolExecutor(2) as pool:
        aw = pool.submit(lambda: owner.post(f"/owner/projects/{pid}/offers/{winner['id']}/approve"))
        su = pool.submit(lambda: admin.post(f"/admin/offers/{winner['id']}/suspend", json={"suspended": True, "reason": "check"}))
        aw, su = aw.result(), su.result()
    db.expire_all()
    o = db.get(Offer, winner["id"])
    # Serialized by the requirement's lock: suspended first -> the award is refused; awarded first -> the
    # award stands (a later suspension is moderation of a decided bid). Never an award of a suspended offer.
    assert su.status_code == 200 and o.is_suspended
    if aw.status_code == 200:
        assert o.status == OfferStatus.approved
    else:
        assert aw.status_code == 400 and o.status == OfferStatus.submitted

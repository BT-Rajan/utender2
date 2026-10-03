"""Stage 3 -- tender & bid integrity, tested through the API like an attacker.

Nothing here looks at the UI. Each test sends the requests a hostile client
could send directly and asserts the rule holds. Tests marked `needs_mysql`
exercise concurrency and need real row locking (SQLite ignores FOR UPDATE);
run them with TEST_DATABASE_URL set.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
import app.routers.offers as offers_module
import app.services.tender_lifecycle as lifecycle_module
from app.auth.security import hash_password
from app.main import app
from app.models.award_record import AwardRecord
from app.models.contractor import ContractorProfile
from app.models.enums import OfferStatus, UserRole, VerificationStatus
from app.models.offer import Offer, OfferRevision
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.user import User

PASSWORD = "password123"
MYSQL = bool(os.environ.get("TEST_DATABASE_URL"))
needs_mysql = pytest.mark.skipif(not MYSQL, reason="needs real row locking (MySQL); SQLite ignores FOR UPDATE")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _future(days=7) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat()


def _owner(db, email="owner@example.com"):
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": PASSWORD, "full_name": "Owner", "role": "owner"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    db.get(OwnerProfile, uid).verification_status = VerificationStatus.approved
    db.commit()
    return c, uid


def _contractor(db, email="c1@example.com", company="Acme Builders"):
    c = TestClient(app)
    r = c.post(
        "/auth/signup",
        json={"email": email, "password": PASSWORD, "full_name": "C", "role": "contractor", "company_name": company},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    p = db.get(ContractorProfile, uid)
    p.verification_status = VerificationStatus.approved
    p.payment_override_active = True
    db.commit()
    return c, uid


def _login(email) -> TestClient:
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return c


def _admin(db):
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="A"))
    db.commit()
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"}).status_code == 200
    return c


def _project(owner, tender_type="owner_visible", status="open", deadline=None) -> str:
    r = owner.post(
        "/projects",
        data={"title": "Job", "address": "1 Main", "bid_deadline": deadline or _future(), "status": status, "tender_type": tender_type},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _bid(contractor, pid, amount="1000.00", **extra):
    return contractor.post(f"/projects/{pid}/offers", json={"amount": amount, **extra})


def _expire_deadline(db, pid, seconds=1):
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=seconds)
    db.commit()


def _offers(db, pid):
    db.expire_all()
    return db.query(Offer).filter_by(project_id=pid).all()


def _awarded_tender(db):
    """owner_visible tender, two bids, closed, c1 awarded."""
    owner, _ = _owner(db)
    c1, c1_id = _contractor(db, "c1@example.com")
    c2, c2_id = _contractor(db, "c2@example.com", "BuildCo")
    pid = _project(owner)
    o1 = _bid(c1, pid, "1000.00").json()["id"]
    o2 = _bid(c2, pid, "1100.00").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/offers/{o1}/approve").status_code == 200
    return owner, c1, c2, pid, o1, o2


# --------------------------------------------------------------------------
# Authorization matrix
# --------------------------------------------------------------------------

OWNER_ROUTES = [
    ("post", "/owner/projects/{pid}/publish"),
    ("post", "/owner/projects/{pid}/close"),
    ("post", "/owner/projects/{pid}/start-evaluation"),
    ("post", "/owner/projects/{pid}/no-award"),
    ("post", "/owner/projects/{pid}/cancel"),
    ("get", "/owner/projects/{pid}/offers"),
    ("get", "/owner/projects/{pid}/offers/{oid}/history"),
    ("post", "/owner/projects/{pid}/offers/{oid}/approve"),
]
CONTRACTOR_ROUTES = [
    ("post", "/projects/{pid}/offers"),
    ("post", "/projects/{pid}/offers/withdraw"),
    ("get", "/projects/{pid}/offers/mine"),
]


def _call(client, method, path, **kw):
    if method == "post" and "offers" in path and path.endswith("/offers"):
        kw.setdefault("json", {"amount": "10.00"})
    return getattr(client, method)(path, **kw)


def test_anonymous_requests_are_rejected_on_every_tender_and_bid_route(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    oid = _bid(c1, pid).json()["id"]

    for method, path in OWNER_ROUTES + CONTRACTOR_ROUTES:
        r = _call(TestClient(app), method, path.format(pid=pid, oid=oid))
        assert r.status_code == 401, (method, path, r.status_code)


def test_wrong_role_is_forbidden_on_owner_and_contractor_routes(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    admin = _admin(db)
    pid = _project(owner)
    oid = _bid(c1, pid).json()["id"]

    for method, path in OWNER_ROUTES:  # a contractor, and an admin, are not an owner
        for who in (c1, admin):
            r = _call(who, method, path.format(pid=pid, oid=oid))
            assert r.status_code == 403, ("non-owner", method, path, r.status_code)
    for method, path in CONTRACTOR_ROUTES:  # an owner, and an admin, are not a contractor
        for who in (owner, admin):
            r = _call(who, method, path.format(pid=pid, oid=oid))
            assert r.status_code == 403, ("non-contractor", method, path, r.status_code)


def test_another_owner_cannot_read_or_change_a_tender_they_do_not_own(db):
    owner_a, _ = _owner(db, "a@example.com")
    owner_b, _ = _owner(db, "b@example.com")
    c1, _ = _contractor(db)
    pid = _project(owner_a)
    oid = _bid(c1, pid).json()["id"]

    for method, path in OWNER_ROUTES:
        r = _call(owner_b, method, path.format(pid=pid, oid=oid))
        assert r.status_code in (403, 404), (method, path, r.status_code)
    for method, path, kw in [
        ("get", f"/projects/{pid}", {}),
        ("get", f"/projects/{pid}/award", {}),
        ("get", f"/projects/{pid}/amendments", {}),
        ("get", f"/projects/{pid}/drawings-zip", {}),
        ("patch", f"/projects/{pid}", {"json": {"title": "Hijacked"}}),
    ]:
        r = getattr(owner_b, method)(path, **kw)
        assert r.status_code in (403, 404), (method, path, r.status_code)

    db.expire_all()
    project = db.get(Project, pid)
    assert project.title == "Job" and project.status.value == "open"
    assert db.get(Offer, oid).status == OfferStatus.submitted


def test_a_contractor_cannot_reach_or_withdraw_another_contractors_bid(db):
    owner, _ = _owner(db)
    c1, c1_id = _contractor(db, "c1@example.com")
    c2, _ = _contractor(db, "c2@example.com", "BuildCo")
    pid = _project(owner)
    oid = _bid(c1, pid, "1000.00").json()["id"]

    assert c2.get(f"/projects/{pid}/offers/mine").json() is None  # sees only their own (none)
    assert c2.get(f"/projects/{pid}/offers/mine/history").json() == []
    assert c2.post(f"/projects/{pid}/offers/withdraw").status_code == 404  # "no offer of yours"
    assert c2.get("/contractor/my-bids").json() == []
    assert c2.get(f"/owner/projects/{pid}/offers/{oid}/history").status_code == 403

    db.expire_all()
    offer = db.get(Offer, oid)
    assert offer.status == OfferStatus.submitted and offer.contractor_id == c1_id


def test_draft_tender_is_invisible_and_unbiddable_for_contractors(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner, status="draft")

    assert c1.get(f"/projects/{pid}").status_code == 404
    assert _bid(c1, pid).status_code == 400
    assert _offers(db, pid) == []


# --------------------------------------------------------------------------
# State machine: invalid transitions are controlled rejections
# --------------------------------------------------------------------------


def test_invalid_lifecycle_transitions_are_rejected_and_change_nothing(db):
    owner, c1_id = None, None
    owner, _ = _owner(db)
    c1, _ = _contractor(db)

    draft = _project(owner, status="draft")
    for action in ("close", "start-evaluation", "no-award"):
        assert owner.post(f"/owner/projects/{draft}/{action}").status_code == 400, action
    assert owner.post(f"/owner/projects/{draft}/offers/none/approve").status_code == 400

    open_pid = _project(owner)
    oid = _bid(c1, open_pid).json()["id"]
    for action in ("publish", "start-evaluation", "no-award"):
        assert owner.post(f"/owner/projects/{open_pid}/{action}").status_code == 400, action
    assert owner.post(f"/owner/projects/{open_pid}/offers/{oid}/approve").status_code == 400  # not closed yet

    awarded_owner, awarded_c1, _c2, awarded_pid, o1, _o2 = _awarded_tender_for(owner, db)
    for action in ("publish", "close", "start-evaluation", "no-award", "cancel"):
        assert owner.post(f"/owner/projects/{awarded_pid}/{action}").status_code == 400, action
    assert owner.post(f"/owner/projects/{awarded_pid}/offers/{o1}/approve").status_code == 400  # no second award
    assert owner.patch(f"/projects/{awarded_pid}", json={"title": "Rewritten"}).status_code == 400

    cancelled = _project(owner)
    assert owner.post(f"/owner/projects/{cancelled}/cancel").status_code == 200
    for action in ("publish", "close", "cancel", "start-evaluation"):
        assert owner.post(f"/owner/projects/{cancelled}/{action}").status_code == 400, action
    assert _bid(c1, cancelled).status_code == 400

    db.expire_all()
    assert db.query(AwardRecord).filter_by(project_id=awarded_pid).count() == 1


def _awarded_tender_for(owner, db):
    c1, _ = _contractor(db, "w1@example.com", "WinCo")
    c2, _ = _contractor(db, "w2@example.com", "LoseCo")
    pid = _project(owner)
    o1 = _bid(c1, pid, "1000.00").json()["id"]
    o2 = _bid(c2, pid, "1100.00").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/offers/{o1}/approve").status_code == 200
    return owner, c1, c2, pid, o1, o2


def test_only_a_live_unsuspended_bid_can_be_awarded(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db, "c1@example.com")
    c2, _ = _contractor(db, "c2@example.com", "BuildCo")
    pid = _project(owner)
    o1 = _bid(c1, pid).json()["id"]
    o2 = _bid(c2, pid).json()["id"]
    assert c2.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200

    assert owner.post(f"/owner/projects/{pid}/offers/{o2}/approve").status_code == 400  # withdrawn
    assert owner.post(f"/owner/projects/{pid}/offers/{o1}/approve").status_code == 200


# --------------------------------------------------------------------------
# Deadline enforcement
# --------------------------------------------------------------------------


def test_bid_after_the_deadline_is_rejected_even_before_the_status_sync(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    _expire_deadline(db, pid)  # status is still "open": nothing has read the project since

    assert _bid(c1, pid).status_code == 400
    assert _offers(db, pid) == []


def test_bid_exactly_at_the_deadline_is_rejected_and_one_instant_before_is_accepted(db, monkeypatch):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    deadline = datetime(2031, 1, 1, 12, 0, 0)
    db.get(Project, pid).bid_deadline = deadline
    db.commit()

    class _Clock(datetime):
        now_value = deadline

        @classmethod
        def utcnow(cls):
            return cls.now_value

    monkeypatch.setattr(offers_module, "datetime", _Clock)
    monkeypatch.setattr(lifecycle_module, "datetime", _Clock)  # where the boundary check lives

    _Clock.now_value = deadline  # the very instant bidding ends: consistent with sync/publish, which use <=
    assert _bid(c1, pid).status_code == 400
    _Clock.now_value = deadline - timedelta(seconds=1)
    assert _bid(c1, pid).status_code == 200


def test_client_supplied_fields_cannot_set_bid_state_or_identity(db):
    owner, _ = _owner(db)
    c1, c1_id = _contractor(db, "c1@example.com")
    _c2, c2_id = _contractor(db, "c2@example.com", "BuildCo")
    pid = _project(owner)
    other = _project(owner)

    r = _bid(
        c1,
        pid,
        "1000.00",
        status="approved",
        contractor_id=c2_id,
        project_id=other,
        revision=99,
        is_suspended=True,
        created_at="2000-01-01T00:00:00",
    )

    assert r.status_code == 200, r.text
    offer = _offers(db, pid)[0]
    assert (offer.status, offer.contractor_id, offer.project_id, offer.revision, offer.is_suspended) == (
        OfferStatus.submitted,
        c1_id,
        pid,
        1,
        False,
    )
    assert _offers(db, other) == []


# --------------------------------------------------------------------------
# Withdrawal and mutability
# --------------------------------------------------------------------------


def test_withdrawal_is_refused_once_bidding_has_closed(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    oid = _bid(c1, pid).json()["id"]
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200

    assert c1.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    db.expire_all()
    assert db.get(Offer, oid).status == OfferStatus.submitted


def test_withdrawal_after_the_deadline_is_refused_even_before_the_status_sync(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    oid = _bid(c1, pid).json()["id"]
    _expire_deadline(db, pid)

    assert c1.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    db.expire_all()
    assert db.get(Offer, oid).status == OfferStatus.submitted


def test_awarded_and_rejected_bids_cannot_be_withdrawn(db):
    _owner_c, c1, c2, pid, o1, o2 = _awarded_tender(db)

    assert c1.post(f"/projects/{pid}/offers/withdraw").status_code == 400  # the winning bid
    assert c2.post(f"/projects/{pid}/offers/withdraw").status_code == 400  # a rejected bid

    db.expire_all()
    assert db.get(Offer, o1).status == OfferStatus.approved
    assert db.get(Offer, o2).status == OfferStatus.rejected
    record = db.query(AwardRecord).filter_by(project_id=pid).one()
    assert record.offer_id == o1 and db.get(Offer, record.offer_id).status == OfferStatus.approved


def test_withdraw_then_resubmit_before_the_deadline_still_works(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    _bid(c1, pid, "1000.00")
    assert c1.post(f"/projects/{pid}/offers/withdraw").status_code == 200

    r = _bid(c1, pid, "900.00")

    assert r.status_code == 200 and r.json()["status"] == "submitted" and r.json()["revision"] == 3
    assert len(_offers(db, pid)) == 1


def test_a_submitted_bid_has_no_edit_route_other_than_resubmission(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    oid = _bid(c1, pid, "1000.00").json()["id"]

    for method, path in [
        ("patch", f"/projects/{pid}/offers/{oid}"),
        ("put", f"/projects/{pid}/offers/{oid}"),
        ("delete", f"/projects/{pid}/offers/{oid}"),
        ("put", f"/projects/{pid}/offers"),
        ("patch", f"/projects/{pid}/offers"),
        ("delete", f"/projects/{pid}/offers"),
    ]:
        r = c1.request(method.upper(), path, json={"amount": "1.00"})
        assert r.status_code in (404, 405), (method, path, r.status_code)

    offer = _offers(db, pid)[0]
    assert offer.amount == Decimal("1000.00") and offer.status == OfferStatus.submitted


def test_resubmitting_after_the_tender_closes_is_refused(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    _bid(c1, pid, "1000.00")
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200

    assert _bid(c1, pid, "1.00").status_code == 400
    assert _offers(db, pid)[0].amount == Decimal("1000.00")


def test_extending_the_deadline_does_not_reopen_a_closed_tender(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    _bid(c1, pid, "1000.00")
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200

    owner.patch(f"/projects/{pid}", json={"bid_deadline": _future(30)})

    db.expire_all()
    assert db.get(Project, pid).status.value == "closed"
    assert _bid(c1, pid, "1.00").status_code == 400


def test_owner_cannot_pull_the_deadline_earlier_once_bids_exist(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner, deadline=_future(10))
    _bid(c1, pid)

    r = owner.patch(f"/projects/{pid}", json={"bid_deadline": _future(1)})

    assert r.status_code == 400


# --------------------------------------------------------------------------
# Sealed-bid confidentiality
# --------------------------------------------------------------------------


def test_cancelling_a_sealed_tender_before_its_deadline_does_not_unseal_its_bids(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner, "sealed")
    oid = _bid(c1, pid, "5000.00").json()["id"]

    assert owner.post(f"/owner/projects/{pid}/cancel").status_code == 200

    offers = owner.get(f"/owner/projects/{pid}/offers").json()
    assert offers and all(o["amount"] is None and o["contractor_id"] is None and o["message"] is None for o in offers)
    assert owner.get(f"/owner/projects/{pid}/offers/{oid}/history").status_code == 404


def test_sealed_bids_stay_hidden_from_every_other_party_and_open_at_the_deadline(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db, "c1@example.com")
    c2, _ = _contractor(db, "c2@example.com", "BuildCo")
    pid = _project(owner, "sealed")
    _bid(c1, pid, "5000.00")

    assert c2.get(f"/projects/{pid}/offers/mine").json() is None
    assert c2.get("/contractor/my-bids").json() == []
    assert "5000" not in c2.get(f"/projects/{pid}").text

    _expire_deadline(db, pid)
    owner.get("/owner/projects")  # lazy sync
    opened = owner.get(f"/owner/projects/{pid}/offers").json()
    assert opened and opened[0]["amount"] is not None and opened[0]["contractor_id"] is not None


# --------------------------------------------------------------------------
# Input validation: controlled rejections, never a 500
# --------------------------------------------------------------------------


@pytest.mark.parametrize("amount", ["0", "-5", "NaN", "Infinity", "abc", "1e400", "10000000000", "99999999999.99"])
def test_unusable_bid_amounts_are_controlled_rejections(db, amount):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)

    r = _bid(c1, pid, amount)

    assert r.status_code in (400, 422), (amount, r.status_code, r.text[:120])
    assert _offers(db, pid) == []


def test_the_largest_amount_the_column_can_hold_is_accepted_exactly(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)

    assert _bid(c1, pid, "9999999999.99").status_code == 200
    assert _offers(db, pid)[0].amount == Decimal("9999999999.99")


def test_overlong_text_fields_are_rejected_not_a_server_error(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)

    assert _bid(c1, pid, "10.00", timeline_estimate="x" * 300).status_code == 422
    assert _bid(c1, pid, "10.00", message="y" * 100_000).status_code == 422
    assert _offers(db, pid) == []


def test_unknown_ids_are_controlled_rejections(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)
    oid = _bid(c1, pid).json()["id"]

    assert _bid(c1, "no-such-tender").status_code == 400
    assert c1.post("/projects/no-such-tender/offers/withdraw").status_code == 404
    assert owner.post("/owner/projects/no-such-tender/close").status_code == 404
    assert owner.post(f"/owner/projects/{pid}/offers/no-such-offer/approve").status_code in (400, 404)
    assert owner.get(f"/owner/projects/no-such-tender/offers/{oid}/history").status_code == 404


# --------------------------------------------------------------------------
# Concurrency (MySQL): serialisation under the project row lock
# --------------------------------------------------------------------------


@needs_mysql
def test_concurrent_first_bids_from_one_contractor_make_one_offer_and_no_errors(db):
    owner, _ = _owner(db)
    _contractor(db, "c1@example.com")
    pid = _project(owner)
    clients = [_login("c1@example.com") for _ in range(8)]

    with ThreadPoolExecutor(8) as pool:
        codes = [r.status_code for r in pool.map(lambda c: _bid(c, pid, "1000.00"), clients)]

    assert codes == [200] * 8, codes
    offers = _offers(db, pid)
    assert len(offers) == 1 and offers[0].revision == 8
    numbers = [r.revision_number for r in db.query(OfferRevision).filter_by(offer_id=offers[0].id)]
    assert sorted(numbers) == list(range(1, 8))  # no duplicated/skipped revision numbers


@needs_mysql
def test_concurrent_awards_of_different_offers_yield_exactly_one_award(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db, "c1@example.com")
    c2, _ = _contractor(db, "c2@example.com", "BuildCo")
    pid = _project(owner)
    o1 = _bid(c1, pid, "1000.00").json()["id"]
    o2 = _bid(c2, pid, "1100.00").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    owners = [_login("owner@example.com"), _login("owner@example.com")]

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda args: args[0].post(f"/owner/projects/{pid}/offers/{args[1]}/approve"), zip(owners, [o1, o2])))

    assert sorted(r.status_code for r in results) == [200, 400], [(r.status_code, r.text[:80]) for r in results]
    db.expire_all()
    assert db.query(AwardRecord).filter_by(project_id=pid).count() == 1
    assert sorted(o.status.value for o in db.query(Offer).filter_by(project_id=pid)) == ["approved", "rejected"]
    assert db.get(Project, pid).status.value == "awarded"


@needs_mysql
def test_a_bid_racing_a_close_is_never_accepted_after_the_close_commits(db):
    owner, _ = _owner(db)
    c1, _ = _contractor(db)
    pid = _project(owner)

    # Play the owner's close mid-transaction: hold the project row, let the bid
    # request start, then commit the close. A correct bid path must wait for the
    # row, re-read the status under the lock, and refuse.
    holder = db_module.engine.connect()
    trans = holder.begin()
    holder.execute(text("SELECT id FROM projects WHERE id = :i FOR UPDATE"), {"i": pid})
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(lambda: _bid(c1, pid, "1000.00"))
        time.sleep(1.0)
        holder.execute(text("UPDATE projects SET status = 'closed' WHERE id = :i"), {"i": pid})
        trans.commit()
        holder.close()
        response = future.result(timeout=30)

    assert response.status_code == 400, response.text
    assert _offers(db, pid) == []

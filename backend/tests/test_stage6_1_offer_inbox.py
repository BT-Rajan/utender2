"""Stage 6.1: the owner's offer inbox -- the submitted offers on one of their
own requirements, each with its status; bounded and in a stable order; nothing
from another requirement or another owner; sealed offers stay sealed."""
from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage4_9_participation import _account
from tests.test_stage5_limitations import _submit, _tender


def _inbox(owner, pid, **params):
    r = owner.get(f"/owner/projects/{pid}/offers", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_inbox_lists_this_requirements_offers_with_their_status(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana"))
    pid, other = _tender(owner, "Inbox"), _tender(owner, "Other")
    for sp in (a, b):
        _submit(sp, pid)
    _submit(c, other)
    a.post(f"/projects/{pid}/offers/withdraw")
    c.post(f"/projects/{pid}/participate")  # a draft is not an offer received

    rows = _inbox(owner, pid)
    assert [(r["service_provider_company_name"], r["status"]) for r in rows] == [("badr", "submitted"), ("amal", "withdrawn")]
    assert all(r["project_id"] == pid and r["submitted_at"] for r in rows)
    # The same order on every refresh, and a page at a time.
    assert _inbox(owner, pid) == rows
    assert [r["id"] for r in _inbox(owner, pid, limit=1, offset=1)] == [rows[1]["id"]]
    assert owner.get(f"/owner/projects/{pid}/offers", params={"limit": 501}).status_code == 422
    # Reading the inbox changes nothing.
    db.expire_all()
    assert db.get(Project, pid).status.value == "open"


def test_no_one_else_reaches_the_inbox_or_its_offers(db):
    owner = _account(db, "owner", "owner@example.com")
    stranger = _account(db, "owner", "stranger@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid, mine_too = _tender(owner, "Mine"), _tender(owner, "Also mine")
    _submit(sp, pid)
    offer_id = _inbox(owner, pid)[0]["id"]
    assert stranger.get(f"/owner/projects/{pid}/offers").status_code == 404
    assert stranger.get(f"/owner/projects/{pid}/offers/{offer_id}/history").status_code == 404
    assert sp.get(f"/owner/projects/{pid}/offers").status_code == 403
    # An offer id under another of the owner's requirements is not found.
    assert owner.get(f"/owner/projects/{mine_too}/offers/{offer_id}/history").status_code == 404
    assert owner.get(f"/owner/projects/{pid}/offers/{offer_id}/history").status_code == 200


def test_an_admin_suspended_offer_stays_out_of_sight_even_by_id(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner, "Moderated")
    _submit(sp, pid)
    offer = db.query(Offer).filter(Offer.project_id == pid).one()
    offer.is_suspended = True
    db.commit()
    assert _inbox(owner, pid) == []
    assert owner.get(f"/owner/projects/{pid}/offers/{offer.id}/history").status_code == 404


def test_a_sealed_inbox_shows_only_that_offers_are_in(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner, "Sealed", sealed=True)
    for sp in (a, b):
        _submit(sp, pid)
    b.post(f"/projects/{pid}/offers/withdraw")
    rows = _inbox(owner, pid)
    assert sorted(r["status"] for r in rows) == ["submitted", "withdrawn"]
    for r in rows:
        assert r["sealed"] is True
        for field in ("service_provider_id", "service_provider_company_name", "amount", "message", "item_prices", "assumptions", "proposed_start_date"):
            assert r.get(field) is None, field
        assert not r.get("documents")
        assert owner.get(f"/owner/projects/{pid}/offers/{r['id']}/history").status_code == 404
    # Ending it early doesn't open it before the deadline.
    assert owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "not_needed"}).status_code == 200
    assert all(r["sealed"] for r in _inbox(owner, pid))


def test_the_inbox_outlasts_the_requirement_closing(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner, "Closing")
    _submit(sp, pid)
    before = _inbox(owner, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    after = _inbox(owner, pid)
    assert [(r["id"], r["status"], r["amount"]) for r in after] == [(r["id"], r["status"], r["amount"]) for r in before]

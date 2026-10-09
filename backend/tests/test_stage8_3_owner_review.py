"""Stage 8.3: the owner side reviews the provider it awarded -- once the
transaction is completed, once per transaction, from an active owner account,
about the actual winner, with a whole-number 1-5 rating and an optional
comment. The review, the provider's recomputed public rating and the audit
entry are one transaction."""
from concurrent.futures import ThreadPoolExecutor

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.services.reviews as reviews_service
from app.main import app
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.owner import OwnerProfile
from app.models.review import Review
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage7_10_completion import _started, _v


def _review(client, pid, rating=5, comment=None):
    return client.post("/owner/reviews", json={"project_id": pid, "rating": rating, "comment": comment})


def _completed(db, owner=None, provider=None, title="HV works"):
    owner = owner or _account(db, "owner", "owner@example.com")
    provider = provider or _account(db, "service_provider", "amal@example.com")
    loser = _account(db, "service_provider", f"loser-{title.replace(' ', '')}@example.com")
    pid = _tender(owner, title=title)
    _submitted(provider, pid)
    _submitted(loser, pid)
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{provider.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    complete_transaction(owner, provider, pid)
    return owner, provider, loser, pid


def test_a_completed_transaction_is_reviewed_once_about_the_actual_winner(db):
    owner, provider, loser, pid = _completed(db)
    r = _review(owner, pid, 4, "  Clean, on time, good documentation.  ")
    assert r.status_code == 200, r.text
    review = r.json()
    award = db.query(AwardRecord).one()
    assert (review["project_id"], review["service_provider_id"], review["rating"], review["comment"]) == (
        pid, award.service_provider_id, 4, "Clean, on time, good documentation.")
    assert review["created_at"].endswith("Z")
    assert owner.get(f"/owner/projects/{pid}/review").json()["id"] == review["id"]
    # Batch C: the review is sealed until both sides have reviewed or 14 days pass --
    # it doesn't count in the provider's public rating yet.
    assert review["revealed"] is False and review["reveals_on"] is not None
    profile = provider.get("/service-provider/profile").json()
    assert (float(profile["avg_rating"]), profile["review_count"]) == (0.0, 0)
    # Batch C: once the sealed period has passed, the review counts.
    stored = db.query(Review).one()
    stored.created_at = stored.created_at - timedelta(days=15)
    db.commit()
    reviews_service.reveal_due(db)
    profile = provider.get("/service-provider/profile").json()
    assert (float(profile["avg_rating"]), profile["review_count"]) == (4.0, 1)
    (entry,) = db.query(AuditLog).filter(AuditLog.action == "review.owner_to_provider").all()
    assert entry.target_id == pid and review["id"] in entry.new_value
    # Once per transaction: a second attempt (a retry, a colleague, another tab) changes nothing.
    again = _review(owner, pid, 1)
    assert again.status_code == 409 and "already been reviewed" in again.json()["detail"]
    assert db.query(Review).count() == 1


def test_only_valid_ratings_and_comments(db):
    owner, provider, loser, pid = _completed(db)
    for bad in (0, 6, -1, 3.5, "5", None):
        assert _review(owner, pid, bad).status_code == 422, bad
    assert _review(owner, pid, 5, "x" * 2001).status_code == 422
    assert db.query(Review).count() == 0
    assert _review(owner, pid, 5, "   ").json()["comment"] is None  # a blank comment is no comment


def test_not_before_completion_and_not_for_other_endings(db):
    owner, provider, other, pid, wid, _ = _started(db)
    assert _review(owner, pid).status_code == 400  # awarded and executing, not completed
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid))
    assert _review(owner, pid).status_code == 400  # terminated
    o = _account(db, "owner", "o2@example.com")
    sp = _account(db, "service_provider", "sp2@example.com")
    draft = o.post("/projects", data={"title": "Draft", "address": "Kaifan", "bid_deadline": "2030-01-01T00:00:00"}).json()["id"]
    assert _review(o, draft).status_code == 400  # a draft
    open_ = _tender(o, title="Open")
    _submitted(sp, open_)
    assert _review(o, open_).status_code == 400  # open, with a submitted offer
    for n, ending in enumerate(("cancel", "no-award", "close-externally")):
        p = _tender(o, title=f"Ended {n}")
        _submitted(sp, p)
        o.post(f"/owner/projects/{p}/close")
        o.post(f"/owner/projects/{p}/{ending}", json={"reason": "other"} if ending != "no-award" else {})
        assert _review(o, p).status_code == 400, ending
    assert db.query(Review).count() == 0


def test_only_the_owner_side_reviews_and_any_member_of_it(db):
    fahad, noura, fahad_id, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    owner, provider, loser, pid = _completed(db, owner=fahad)
    for client in (provider, loser):  # providers -- the winner included -- can't review here
        assert _review(client, pid).status_code == 403
    assert _review(_account(db, "owner", "other@example.com", organization="Other Co"), pid).status_code == 404
    assert _review(TestClient(app), pid).status_code == 401
    # A suspended owner organisation can't record a review.
    profile = db.get(OwnerProfile, fahad_id)
    profile.is_suspended = True
    db.commit()
    assert _review(noura, pid).status_code == 403
    profile.is_suspended = False
    db.commit()
    assert _review(noura, pid).status_code == 200  # the colleague who didn't award it: the organisation's review
    assert fahad.get(f"/owner/projects/{pid}/review").json()["rating"] == 5


def test_a_failed_save_records_nothing(db, monkeypatch):
    owner, provider, loser, pid = _completed(db)

    def failing_log(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(reviews_service.audit, "log_action", failing_log)
    with pytest.raises(RuntimeError):
        _review(owner, pid)
    monkeypatch.undo()
    db.expire_all()
    sp = db.get(ServiceProviderProfile, db.query(AwardRecord).one().service_provider_id)
    assert db.query(Review).count() == 0 and sp.review_count == 0  # no review, no half-updated rating


@needs_mysql
def test_two_members_reviewing_at_once_record_one_review(db):
    fahad, noura, *_ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    owner, provider, loser, pid = _completed(db, owner=fahad)

    def login(email):
        c = TestClient(app)
        c.post("/auth/login", json={"email": email, "password": "password123"})
        return c

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(f.result().status_code for f in [pool.submit(lambda e=e: _review(login(e), pid)) for e in ("fahad@gulf.example", "noura@gulf.example")])
    assert codes == [200, 409], codes
    db.expire_all()
    assert db.query(Review).count() == 1
    # Batch C: sealed until revealed; once its sealed period has passed, it counts once.
    provider_id = db.query(AwardRecord).one().service_provider_id
    assert db.get(ServiceProviderProfile, provider_id).review_count == 0
    db.query(Review).one().created_at = datetime.utcnow() - timedelta(days=15)
    db.commit()
    assert reviews_service.reveal_due(db) == 1
    db.expire_all()
    assert db.get(ServiceProviderProfile, provider_id).review_count == 1

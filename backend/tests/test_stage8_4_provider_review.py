"""Stage 8.4: the winning provider reviews the owner -- the same review
record and rules as 8.3, in the other direction: once the transaction is
completed, once per transaction, about the requirement's owner (from the
transaction, never the request), by any member of the winning provider's
side, under the requirement's lock; each side reads only its own review; the
reviewed party is told. Also the 8.3 fix: the provider is told when the owner
reviews it."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.project import Project
from app.models.review import Review
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage7_10_completion import _started, _v


def _review(client, pid, rating=4, **extra):
    return client.post("/service-provider/reviews", json={"project_id": pid, "rating": rating, **extra})


def _world(db, complete=True):
    owner, colleague, owner_id, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, amal_id, _ = _organization(db, "service_provider", "Amal Contracting", "amal@amal.example", "sami@amal.example")
    loser = _account(db, "service_provider", "loser@example.com")
    pid = _tender(owner, title="Tower maintenance")
    _submitted(sami, pid)
    _submitted(loser, pid)
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{sami.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    if complete:
        complete_transaction(owner, sami, pid)
    return dict(owner=owner, colleague=colleague, owner_id=owner_id, amal=amal, sami=sami, amal_id=amal_id, loser=loser, pid=pid)


def _notified(db, client, link):
    uid = client.get("/auth/me").json()["id"]
    return db.query(Notification).filter(Notification.user_id == uid, Notification.type == NotificationType.review_received, Notification.link == link).count()


def test_the_winner_reviews_the_owner_once_and_sees_its_own_review(db):
    w = _world(db)
    pid = w["pid"]
    assert w["sami"].get(f"/service-provider/projects/{pid}/review").json() is None  # the review is available
    r = _review(w["sami"], pid, 4, comment="  Clear scope, prompt decisions.  ",
                owner_id="someone-else", service_provider_id="someone-else")  # tampered ids are ignored
    assert r.status_code == 200, r.text
    review = r.json()
    project = db.get(Project, pid)
    assert (review["direction"], review["owner_id"], review["service_provider_id"], review["rating"], review["comment"]) == (
        "provider_to_owner", project.owner_id, w["amal_id"], 4, "Clear scope, prompt decisions.")
    assert review["created_at"].endswith("Z")
    assert db.query(Review).one().reviewer_id == w["sami"].get("/auth/me").json()["id"]
    # Any member of the winning side sees the organisation's review; the owner side doesn't (visibility is 8.6).
    assert w["amal"].get(f"/service-provider/projects/{pid}/review").json()["id"] == review["id"]
    assert w["owner"].get(f"/owner/projects/{pid}/review").json() is None
    # Once per transaction: a retry, a colleague, a second tab.
    for client in (w["sami"], w["amal"]):
        again = _review(client, pid, 1)
        assert again.status_code == 409 and "already been reviewed" in again.json()["detail"]
    assert db.query(Review).count() == 1
    # The owner side is told; the provider's public rating isn't touched by a review it wrote.
    for client in (w["owner"], w["colleague"]):
        assert _notified(db, client, f"/owner/projects/{pid}") == 1
    assert db.get(ServiceProviderProfile, w["amal_id"]).review_count == 0
    assert db.query(AuditLog).filter(AuditLog.action == "review.provider_to_owner").count() == 1


def test_both_directions_stand_side_by_side_and_the_provider_is_told_of_its_review(db):
    w = _world(db)
    pid = w["pid"]
    assert w["owner"].post("/owner/reviews", json={"project_id": pid, "rating": 5}).status_code == 200
    for client in (w["amal"], w["sami"]):  # the 8.3 fix: every member of the winning side is told
        assert _notified(db, client, f"/service-provider/projects/{pid}/offer") == 1
    assert _notified(db, w["loser"], f"/service-provider/projects/{pid}/offer") == 0
    assert _review(w["sami"], pid, 3).status_code == 200
    assert sorted(r.direction for r in db.query(Review)) == ["owner_to_provider", "provider_to_owner"]
    profile = w["amal"].get("/service-provider/profile").json()
    assert (float(profile["avg_rating"]), profile["review_count"]) == (5.0, 1)  # only the owner's review counts
    assert w["owner"].get(f"/owner/projects/{pid}/review").json()["direction"] == "owner_to_provider"
    assert w["sami"].get(f"/service-provider/projects/{pid}/review").json()["direction"] == "provider_to_owner"


def test_no_review_without_a_completed_transaction_of_ones_own(db):
    w = _world(db, complete=False)
    pid = w["pid"]
    assert _review(w["sami"], pid).status_code == 400  # awarded, not completed
    for client in (w["loser"], _account(db, "service_provider", "rival@example.com", organization="Rival Co")):
        assert _review(client, pid).status_code == 404  # not the winner
        assert client.get(f"/service-provider/projects/{pid}/review").status_code == 404
    assert _review(w["owner"], pid).status_code == 403  # an owner can't use the provider's review
    assert TestClient(app).post("/service-provider/reviews", json={"project_id": pid, "rating": 4}).status_code == 401
    # Another completed transaction of the same owner, won by someone else: not this provider's to review.
    other_sp = _account(db, "service_provider", "dana@example.com")
    pid2 = _tender(w["owner"], title="Second")
    _submitted(other_sp, pid2)
    w["owner"].post(f"/owner/projects/{pid2}/close")
    w["owner"].post(f"/owner/projects/{pid2}/offers/{other_sp.get(f'/projects/{pid2}/offers/mine').json()['id']}/approve")
    complete_transaction(w["owner"], other_sp, pid2)
    assert _review(w["sami"], pid2).status_code == 404
    assert db.query(Review).count() == 0


def test_other_endings_and_invalid_input(db):
    owner, a, b, pid, wid, _ = _started(db)
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid))
    assert _review(a, pid).status_code == 400  # terminated
    o = _account(db, "owner", "o2@example.com")
    sp = _account(db, "service_provider", "sp2@example.com")
    p = _tender(o, title="Cancelled")
    _submitted(sp, p)
    o.post(f"/owner/projects/{p}/close")
    o.post(f"/owner/projects/{p}/cancel", json={"reason": "other"})
    assert _review(sp, p).status_code == 404  # no award, no winner
    w = _world(db)
    for bad in (0, 6, 2.5, "4"):
        assert _review(w["sami"], w["pid"], bad).status_code == 422, bad
    assert _review(w["sami"], w["pid"], 4, comment="x" * 2001).status_code == 422
    assert db.query(Review).count() == 0


def test_a_suspended_winner_cannot_review(db):
    w = _world(db)
    profile = db.get(ServiceProviderProfile, w["amal_id"])
    profile.is_suspended = True
    db.commit()
    assert _review(w["sami"], w["pid"]).status_code == 403
    assert db.query(Review).count() == 0


@needs_mysql
def test_two_members_reviewing_at_once_record_one_review(db):
    w = _world(db)

    def login(email):
        c = TestClient(app)
        c.post("/auth/login", json={"email": email, "password": "password123"})
        return c

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(f.result().status_code for f in [pool.submit(lambda e=e: _review(login(e), w["pid"])) for e in ("amal@amal.example", "sami@amal.example")])
    assert codes == [200, 409], codes
    db.expire_all()
    assert db.query(Review).count() == 1

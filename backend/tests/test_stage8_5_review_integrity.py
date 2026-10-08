"""Stage 8.5: review integrity, both directions. Only a participant of a
genuinely completed transaction creates its review; the parties, reviewer and
transaction come from the server; one review per direction; reviews can't be
edited, deleted or reached by id; the database itself refuses a review in no
direction or between a party and itself."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

REFUSED = (IntegrityError, OperationalError)  # MySQL reports a failed CHECK as OperationalError (3819)

from app.main import app
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.project import Project
from app.models.review import Review
from tests.stage7_helpers import complete_transaction
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_4_provider_review import _world

OWNER_POST, PROVIDER_POST = "/owner/reviews", "/service-provider/reviews"


def _two_transactions(db):
    w = _world(db)
    # Transaction B: the same owner, another provider, also completed.
    other = _account(db, "service_provider", "dana@example.com")
    pid_b = _tender(w["owner"], title="Second job")
    _submitted(other, pid_b)
    w["owner"].post(f"/owner/projects/{pid_b}/close")
    w["owner"].post(f"/owner/projects/{pid_b}/offers/{other.get(f'/projects/{pid_b}/offers/mine').json()['id']}/approve")
    complete_transaction(w["owner"], other, pid_b)
    return w, other, pid_b


def test_abuse_attempts_produce_no_review(db):
    w, other, pid_b = _two_transactions(db)
    pid = w["pid"]
    outsider_owner = _account(db, "owner", "mallory@example.com", organization="Other Holdings")
    attempts = [
        (w["loser"], PROVIDER_POST, pid, 404),         # A: a losing provider reviewing the owner
        (outsider_owner, OWNER_POST, pid, 404),         # B: an unrelated owner reviewing the provider
        (w["sami"], PROVIDER_POST, pid_b, 404),          # C: a participant of A using transaction B
        (other, PROVIDER_POST, pid, 404),               # C: the reverse
        (w["sami"], OWNER_POST, pid, 403),              # direction swap: a provider through the owner endpoint
        (w["owner"], PROVIDER_POST, pid, 403),          # and an owner through the provider endpoint
        (TestClient(app), OWNER_POST, pid, 401),        # J: no session
        (TestClient(app), PROVIDER_POST, pid, 401),
    ]
    for client, path, project_id, expected in attempts:
        r = client.post(path, json={"project_id": project_id, "rating": 1})
        assert r.status_code == expected, (path, project_id, r.status_code, r.text)
    assert db.query(Review).count() == 0
    assert db.query(Notification).filter(Notification.type == NotificationType.review_received).count() == 0  # no false notifications


def test_valid_reviews_are_bound_to_their_transaction_whatever_the_request_says(db):
    w, other, pid_b = _two_transactions(db)
    pid = w["pid"]
    tamper = {"owner_id": "x", "service_provider_id": db.get(Project, pid_b).owner_id, "reviewer_id": "x", "direction": "owner_to_provider", "id": "x"}
    a = w["owner"].post(OWNER_POST, json={"project_id": pid, "rating": 5, **tamper})
    b = w["sami"].post(PROVIDER_POST, json={"project_id": pid, "rating": 4, **tamper})  # D: subject substitution ignored
    assert a.status_code == b.status_code == 200
    project = db.get(Project, pid)
    rows = {r.direction: r for r in db.query(Review)}
    assert set(rows) == {"owner_to_provider", "provider_to_owner"}
    for r in rows.values():
        assert (r.project_id, r.owner_id, r.service_provider_id) == (pid, project.owner_id, w["amal_id"])
        assert r.owner_id != r.service_provider_id and r.created_at is not None
    assert rows["owner_to_provider"].reviewer_id == w["owner"].get("/auth/me").json()["id"]
    assert rows["provider_to_owner"].reviewer_id == w["sami"].get("/auth/me").json()["id"]
    # E: the same participant again -- one review per direction stays.
    assert w["owner"].post(OWNER_POST, json={"project_id": pid, "rating": 1}).status_code == 409
    assert w["amal"].post(PROVIDER_POST, json={"project_id": pid, "rating": 1}).status_code == 409
    assert db.query(Review).count() == 2
    # H: no endpoint edits, deletes or reaches a review by its id.
    rid = rows["owner_to_provider"].id
    for client, method, path in ((w["owner"], "put", f"/owner/reviews/{rid}"), (w["owner"], "delete", f"/owner/reviews/{rid}"),
                                 (w["owner"], "patch", f"/owner/reviews/{rid}"), (w["sami"], "delete", f"/service-provider/reviews/{rid}"),
                                 (w["owner"], "get", f"/owner/reviews/{rid}")):
        assert getattr(client, method)(path).status_code in (404, 405), (method, path)
    db.expire_all()
    assert db.get(Review, rid).rating == 5
    # Each side reads only its own review; nothing of the other transaction leaks.
    assert w["owner"].get(f"/owner/projects/{pid}/review").json()["direction"] == "owner_to_provider"
    assert w["sami"].get(f"/service-provider/projects/{pid}/review").json()["direction"] == "provider_to_owner"
    assert w["sami"].get(f"/service-provider/projects/{pid_b}/review").status_code == 404


def test_membership_and_suspension_are_checked_at_submission(db):
    w = _world(db)
    pid = w["pid"]
    # I: a member removed from the winning organisation can't use its old standing.
    sami_id = w["sami"].get("/auth/me").json()["id"]
    assert w["amal"].delete(f"/account/organization/members/{sami_id}").status_code == 200
    assert w["sami"].post(PROVIDER_POST, json={"project_id": pid, "rating": 4}).status_code in (403, 404)  # no longer an approved member of the winner
    # A requirement suspended by an admin takes no review from either side.
    project = db.get(Project, pid)
    project.is_suspended = True
    db.commit()
    assert w["owner"].post(OWNER_POST, json={"project_id": pid, "rating": 4}).status_code == 400
    assert w["amal"].post(PROVIDER_POST, json={"project_id": pid, "rating": 4}).status_code == 404
    project.is_suspended = False
    db.commit()
    assert w["owner"].post(OWNER_POST, json={"project_id": pid, "rating": 4}).status_code == 200
    assert db.query(Review).count() == 1


def test_the_database_refuses_impossible_reviews(db):
    w = _world(db)
    project = db.get(Project, w["pid"])
    for direction, owner_id, provider_id in (("sideways", project.owner_id, w["amal_id"]), ("owner_to_provider", w["amal_id"], w["amal_id"])):
        db.add(Review(project_id=project.id, owner_id=owner_id, service_provider_id=provider_id, direction=direction, rating=3))
        with pytest.raises(REFUSED):
            db.commit()
        db.rollback()
    for bad in (0, 6):
        db.add(Review(project_id=project.id, owner_id=project.owner_id, service_provider_id=w["amal_id"], direction="owner_to_provider", rating=bad))
        with pytest.raises(REFUSED):
            db.commit()
        db.rollback()
    db.add(Review(project_id=project.id, owner_id=project.owner_id, service_provider_id=w["amal_id"], direction="owner_to_provider", rating=3))
    db.add(Review(project_id=project.id, owner_id=project.owner_id, service_provider_id=w["amal_id"], direction="owner_to_provider", rating=4))
    with pytest.raises(IntegrityError):  # one per direction, even bypassing the application
        db.commit()
    db.rollback()

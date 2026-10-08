"""Stage 8.9: the reviewed side may give one, final response to a review it
received -- beside the review, which never changes (reviews stay immutable:
there is no edit or delete path), so ratings and reputations don't move.
Only the reviewed organisation's current members may respond; the response is
seen wherever the review is (8.6) and nowhere else; the reviewer is told."""
from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.review import Review
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award

SCOPE = "The project was completed, but the final scope changed during execution."


def _respond(client, side, pid, text):
    return client.post(f"/{side}/projects/{pid}/review/received/response", json={"response": text})


def _told(db, client):
    uid = client.get("/auth/me").json()["id"]
    return db.query(Notification).filter(Notification.user_id == uid, Notification.type == NotificationType.review_response).count()


def test_the_reviewed_side_responds_once_and_the_review_stands(db):
    owner, noura, _, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, _, _ = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    y = _account(db, "service_provider", "y@example.com", organization="Y Co")
    pid = _tender(owner, title="Tower maintenance")
    _award(owner, sami, pid, y)
    complete_transaction(owner, sami, pid)

    # Nothing to respond to yet.
    assert _respond(owner, "owner", pid, SCOPE).status_code == 404

    # Scenario 1: X gives the owner 3/5; the owner organisation responds.
    assert sami.post("/service-provider/reviews", json={"project_id": pid, "rating": 3, "comment": "Scope kept moving."}).status_code == 200
    before = db.query(Review).one()
    original = (before.id, before.rating, before.comment, before.reviewer_id, before.owner_id, before.service_provider_id, before.created_at)
    assert _respond(owner, "owner", pid, "   ").status_code == 400
    assert _respond(owner, "owner", pid, "x" * 2001).status_code == 422
    r = _respond(noura, "owner", pid, f"  {SCOPE}  ")
    assert r.status_code == 200 and r.json()["response"] == SCOPE and r.json()["response_at"].endswith("Z")
    assert (r.json()["rating"], r.json()["comment"]) == (3, "Scope kept moving.")
    db.expire_all()
    after = db.query(Review).one()
    assert (after.id, after.rating, after.comment, after.reviewer_id, after.owner_id, after.service_provider_id, after.created_at) == original
    assert after.responded_by == noura.get("/auth/me").json()["id"]
    assert db.query(AuditLog).filter(AuditLog.action == "review.response.provider_to_owner").count() == 1
    # Once only -- a colleague, a retry; nobody else can respond as the owner.
    assert _respond(owner, "owner", pid, "Second thoughts.").status_code == 409
    assert _respond(_account(db, "owner", "other@example.com"), "owner", pid, "Hijack").status_code == 404
    assert _respond(sami, "owner", pid, "Hijack").status_code == 403  # the reviewer can't speak for the owner
    rep = owner.get("/owner/reputation").json()
    assert (rep["review_count"], rep["avg_rating"]) == (1, 3.0)
    assert rep["recent_reviews"][0]["response"] == SCOPE
    # The reviewer's side sees the response beside its own review, and is told.
    assert amal.get(f"/service-provider/projects/{pid}/review").json()["response"] == SCOPE
    assert (_told(db, amal), _told(db, sami), _told(db, owner)) == (1, 1, 0)

    # Scenario 2: the owner gives X 2/5; only X's organisation can respond.
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 2, "comment": "Late handover."}).status_code == 200
    assert _respond(owner, "service-provider", pid, "Impersonation").status_code == 403
    # Scenario 3: Y, who lost this tender, can't respond to the review about X.
    assert _respond(y, "service-provider", pid, "Not mine to answer").status_code == 404
    assert db.query(Review).filter(Review.response.isnot(None)).count() == 1
    assert _respond(amal, "service-provider", pid, "Handover waited on site access.").status_code == 200
    rep = amal.get("/service-provider/reputation").json()
    assert (rep["completed_transactions"], rep["review_count"], rep["avg_rating"]) == (1, 1, 2.0)
    assert owner.get(f"/owner/projects/{pid}/review").json()["response"] == "Handover waited on site access."
    assert (_told(db, owner), _told(db, noura)) == (1, 1)
    assert db.query(Review).count() == 2

    # Scenario 4: reviews stay immutable -- no edit or delete path exists, and a resubmission is refused.
    rid = db.query(Review).filter(Review.direction == "owner_to_provider").one().id
    for method, path in (("put", f"/owner/reviews/{rid}"), ("patch", f"/owner/reviews/{rid}"), ("delete", f"/owner/reviews/{rid}"),
                         ("put", "/service-provider/reviews"), ("delete", f"/service-provider/reviews/{rid}")):
        assert getattr(owner, method)(path).status_code in (404, 405)
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 5}).status_code == 409
    assert amal.get("/service-provider/reputation").json()["avg_rating"] == 2.0

    # Scenario 5: the response goes only where the review goes. An owner weighing X sees it with
    # the review; a provider weighing the owner sees neither (counts only); outsiders see nothing.
    other = _account(db, "owner", "other2@example.com")
    p2 = _tender(other, title="Open tender")
    _submitted(amal, p2)
    offer = amal.get(f"/projects/{p2}/offers/mine").json()["id"]
    seen = other.get(f"/owner/projects/{p2}/offers/{offer}/reputation").json()
    assert seen["recent_reviews"][0]["response"] == "Handover waited on site access."
    p3 = _tender(owner, title="New tender")
    assert y.get(f"/projects/{p3}/owner-reputation").json()["recent_reviews"] == []
    assert SCOPE not in y.get(f"/projects/{p3}/owner-reputation").text
    assert y.get(f"/service-provider/projects/{pid}/review/received").status_code == 404
    assert TestClient(app).post(f"/owner/projects/{pid}/review/received/response", json={"response": "x"}).status_code == 401
    # A removed member can no longer read or respond for the organisation.
    assert owner.delete(f"/account/organization/members/{noura_id}").status_code == 200
    assert noura.get(f"/owner/projects/{pid}/review/received").status_code == 404

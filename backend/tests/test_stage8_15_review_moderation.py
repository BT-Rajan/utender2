"""Stage 8.15: a party may report the review about it, or the response to its
own review; a report changes nothing by itself. An admin keeps or hides what
was reported: the row and the audit remain, a hidden review stops being shown
or counted (stored and live ratings alike), a hidden response stops being
shown. Nobody else can report, read reports or moderate."""
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.review import Review, ReviewReport
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from tests.stage7_helpers import complete_transaction
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award

ABUSE = "<script>alert(1)</script> Call me on 9999 9999 or else."


def _admin(db):
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    c = TestClient(app)
    c.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    return c


def test_reports_change_nothing_until_an_admin_decides(db):
    a = _account(db, "owner", "a@example.com")
    x = _account(db, "service_provider", "x@example.com", organization="X Co")
    y = _account(db, "service_provider", "y@example.com", organization="Y Co")
    other = _account(db, "owner", "b@example.com")
    admin = _admin(db)
    x_id = x.get("/auth/me").json()["id"]
    p1 = _tender(a, title="First job")
    _award(a, x, p1, y)
    complete_transaction(a, x, p1)

    # 1-4. A's legitimate 2/5 review; X responds, then reports it. Nothing changes.
    assert a.post("/owner/reviews", json={"project_id": p1, "rating": 2, "comment": "Late and untidy."}).status_code == 200
    assert x.post(f"/service-provider/projects/{p1}/review/received/response", json={"response": ABUSE}).status_code == 200
    r = x.post(f"/service-provider/projects/{p1}/review-reports", json={"target": "review", "reason": "other", "note": "We disagree."})
    assert r.status_code == 201 and r.json()["status"] == "open"
    assert x.post(f"/service-provider/projects/{p1}/review-reports", json={"target": "review", "reason": "abusive"}).status_code == 409
    assert x.post(f"/service-provider/projects/{p1}/review-reports", json={"target": "review", "reason": "spam"}).status_code == 422
    assert x.post(f"/service-provider/projects/{p1}/review-reports", json={"target": "response", "reason": "other"}).status_code == 404  # X wrote no review
    # 5. Still shown and counted.
    assert x.get(f"/service-provider/projects/{p1}/review/received").json()["rating"] == 2
    assert (x.get("/service-provider/reputation").json()["review_count"], x.get("/service-provider/reputation").json()["avg_rating"]) == (1, 2.0)
    # A (the reviewer) reports X's response.
    assert a.post(f"/owner/projects/{p1}/review-reports", json={"target": "response", "reason": "private_information"}).status_code == 201

    # 12 / 16. Nobody else reports, reads or decides.
    assert y.post(f"/service-provider/projects/{p1}/review-reports", json={"target": "review", "reason": "abusive"}).status_code == 404
    assert other.post(f"/owner/projects/{p1}/review-reports", json={"target": "review", "reason": "abusive"}).status_code == 404
    assert TestClient(app).post(f"/owner/projects/{p1}/review-reports", json={"target": "review", "reason": "abusive"}).status_code == 401
    rid = db.query(ReviewReport).filter(ReviewReport.target == "review").one().id
    for c in (a, x, y):
        assert c.get("/admin/review-reports").status_code == 403
        assert c.post(f"/admin/review-reports/{rid}/decision", json={"decision": "hide"}).status_code == 403
    # 10-11. Neither side can rewrite the other's words: there is no such path.
    assert x.patch("/owner/reviews", json={"rating": 5}).status_code in (403, 404, 405)
    assert a.post(f"/service-provider/projects/{p1}/review/received/response", json={"response": "x"}).status_code == 403

    # 6-7. The admin sees both reports (open first), the content and the parties -- and keeps the legitimate review.
    reports = admin.get("/admin/review-reports").json()
    assert [r["status"] for r in reports] == ["open", "open"] and "@" not in str(reports)
    by_target = {r["target"]: r for r in reports}
    assert by_target["review"]["reported_by"] == "service_provider" and by_target["response"]["reported_by"] == "owner"
    assert by_target["review"]["comment"] == "Late and untidy." and by_target["response"]["response"] == ABUSE
    kept = admin.post(f"/admin/review-reports/{rid}/decision", json={"decision": "keep", "note": "A fair review."})
    assert kept.status_code == 200 and kept.json()["status"] == "kept"
    assert admin.post(f"/admin/review-reports/{rid}/decision", json={"decision": "hide"}).status_code == 409  # decided once
    assert x.get("/service-provider/reputation").json()["avg_rating"] == 2.0
    # 8. The abusive response is hidden: no longer shown anywhere, the row and the rating intact.
    resp_id = by_target["response"]["id"]
    assert admin.post(f"/admin/review-reports/{resp_id}/decision", json={"decision": "hide"}).json()["status"] == "hidden"
    assert a.get(f"/owner/projects/{p1}/review").json()["response"] is None
    assert x.get(f"/service-provider/projects/{p1}/review/received").json()["response"] is None
    assert x.get("/service-provider/reputation").json()["recent_reviews"][0]["response"] is None
    assert db.query(Review).filter(Review.project_id == p1).one().response == ABUSE  # kept on record

    # 9. A review hidden by moderation stops counting -- live and stored -- but stays on record and unrepeatable.
    p2 = _tender(a, title="Second job")
    _award(a, x, p2)
    complete_transaction(a, x, p2)
    assert a.post("/owner/reviews", json={"project_id": p2, "rating": 5, "comment": "Threatening text"}).status_code == 200
    assert x.get("/service-provider/reputation").json()["avg_rating"] == 3.5
    assert x.post(f"/service-provider/projects/{p2}/review-reports", json={"target": "review", "reason": "abusive"}).status_code == 201
    rid2 = db.query(ReviewReport).filter(ReviewReport.status == "open").one().id
    assert admin.post(f"/admin/review-reports/{rid2}/decision", json={"decision": "hide"}).status_code == 200
    rep = x.get("/service-provider/reputation").json()
    assert (rep["completed_transactions"], rep["review_count"], rep["avg_rating"]) == (2, 1, 2.0)
    profile = db.get(ServiceProviderProfile, x_id)
    db.refresh(profile)
    assert (profile.review_count, float(profile.avg_rating)) == (1, 2.0)
    assert x.get(f"/service-provider/projects/{p2}/review/received").json() is None
    assert a.get(f"/owner/projects/{p2}/review").json()["hidden"] is True
    assert a.post("/owner/reviews", json={"project_id": p2, "rating": 1}).status_code == 409  # no second review
    assert x.post(f"/service-provider/projects/{p2}/review/received/response", json={"response": "x"}).status_code == 404
    hidden = db.query(Review).filter(Review.project_id == p2).one()
    assert (hidden.rating, hidden.service_provider_id, hidden.direction) == (5, x_id, "owner_to_provider")
    assert db.query(AuditLog).filter(AuditLog.action.like("review.report.%")).count() == 3
    assert db.query(AuditLog).filter(AuditLog.action.like("review.moderation.%")).count() == 3

    # 13-15. Duplicates, cancelled tenders and invented relationships still create nothing.
    p3 = _tender(a, title="Cancelled")
    _submitted(x, p3)
    a.post(f"/owner/projects/{p3}/close")
    a.post(f"/owner/projects/{p3}/cancel", json={"reason": "other"})
    assert a.post("/owner/reviews", json={"project_id": p3, "rating": 1}).status_code == 400
    assert x.post("/service-provider/reviews", json={"project_id": p3, "rating": 1, "owner_id": "x"}).status_code == 404
    assert db.query(Review).count() == 2

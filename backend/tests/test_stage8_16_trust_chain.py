"""Stage 8.16: the Stage 8 chain end to end -- completed transaction, one
review each way (or only one), responses, a report decided by an admin,
reputations, a repeat requirement where the previous provider and a new one
compete on their offers alone -- and the endings that never produce a review
(terminated, cancelled, lost). The old transaction stays as it was."""
from datetime import timedelta

from app.models.agreement import Agreement
from app.models.review import Review
from app.services.reviews import reveal_due
from tests.stage7_helpers import complete_transaction
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage7_10_completion import _started, _v
from tests.test_stage8_7_provider_reputation import _award
from tests.test_stage8_15_review_moderation import _admin


def test_the_whole_chain(db):
    a = _account(db, "owner", "a@example.com", organization="Owner A")
    x = _account(db, "service_provider", "x@example.com", organization="X Co")
    y = _account(db, "service_provider", "y@example.com", organization="Y Co")
    z = _account(db, "service_provider", "z@example.com", organization="Z Co")  # no history
    admin = _admin(db)
    # 1. Completed: both review; 10. responses leave the reviews intact.
    p1 = _tender(a, title="Job one")
    _award(a, x, p1, y)
    assert a.post("/owner/reviews", json={"project_id": p1, "rating": 4}).status_code == 400  # not before completion
    complete_transaction(a, x, p1)
    assert a.post("/owner/reviews", json={"project_id": p1, "rating": 4, "comment": "Good."}).status_code == 200
    assert x.post("/service-provider/reviews", json={"project_id": p1, "rating": 5}).status_code == 200
    assert x.post(f"/service-provider/projects/{p1}/review/received/response", json={"response": "Thanks."}).status_code == 200
    # 5-6. The loser and a duplicate are refused.
    assert y.post("/service-provider/reviews", json={"project_id": p1, "rating": 1}).status_code == 404
    assert a.post("/owner/reviews", json={"project_id": p1, "rating": 1}).status_code == 409
    # 2. Another completed with Y: only the owner reviews.
    p2 = _tender(a, title="Job two")
    _award(a, y, p2)
    complete_transaction(a, y, p2)
    assert a.post("/owner/reviews", json={"project_id": p2, "rating": 2}).status_code == 200
    assert y.get(f"/service-provider/projects/{p2}/review").json() is None
    # Batch C: Y doesn't review back, so the owner's review stays sealed (not reportable) for 14 days.
    assert y.post(f"/service-provider/projects/{p2}/review-reports", json={"target": "review", "reason": "other"}).status_code == 404
    assert y.get("/service-provider/reputation").json()["review_count"] == 0
    sealed = db.query(Review).filter(Review.project_id == p2).one()
    sealed.created_at = sealed.created_at - timedelta(days=15)
    db.commit()
    reveal_due(db)
    # 8. Y reports the 2/5: nothing changes; 9. the admin keeps it (a legitimate negative review stays).
    assert y.post(f"/service-provider/projects/{p2}/review-reports", json={"target": "review", "reason": "other"}).status_code == 201
    assert y.get("/service-provider/reputation").json()["avg_rating"] == 2.0
    report = admin.get("/admin/review-reports").json()[0]
    assert admin.post(f"/admin/review-reports/{report['id']}/decision", json={"decision": "keep"}).json()["status"] == "kept"
    assert y.post(f"/service-provider/projects/{p2}/review-reports", json={"target": "review", "reason": "other"}).json()["detail"].startswith("This has already been reported")
    # Reputations: owner reviews for providers, provider reviews for the owner -- never mixed.
    assert [(r["completed_transactions"], r["review_count"], r["avg_rating"]) for r in (
        x.get("/service-provider/reputation").json(), y.get("/service-provider/reputation").json(), a.get("/owner/reputation").json())] == [
        (1, 1, 4.0), (1, 1, 2.0), (2, 1, 5.0)]
    before = (db.query(Agreement).filter(Agreement.project_id == p1).one().completed_at, db.query(Review).count())

    # 11-14. A repeat requirement: X recognised, Z (new) neutral, offers in their usual order; Z wins on its offer.
    p3 = a.post(f"/owner/projects/{p1}/restart").json()["id"]
    assert a.get(f"/owner/projects/{p3}/offers").json() == []
    assert a.post(f"/owner/projects/{p3}/publish").status_code == 200
    for p in (x, y, z):
        _submitted(p, p3)
    a.post(f"/owner/projects/{p3}/close")
    offers = a.get(f"/owner/projects/{p3}/offers").json()
    signals = {o["service_provider_company_name"]: (o["service_provider_completed_transactions"], o["completed_with_you"]) for o in offers}
    assert signals == {"x": (1, 1), "y": (1, 1), "z": (0, 0)}
    assert [o["id"] for o in offers] == [o["id"] for o in sorted(offers, key=lambda o: (o["submitted_at"], o["id"]))]
    assert [p["company_name"] for p in a.get("/owner/previous-providers").json()] in (["x", "y"], ["y", "x"])
    assert [o["owner_name"] for o in x.get("/service-provider/previous-owners").json()] == ["Owner A"]
    z_offer = next(o["id"] for o in offers if o["service_provider_company_name"] == "z")
    assert a.post(f"/owner/projects/{p3}/offers/{z_offer}/approve").status_code == 200
    # 15-16. The old transaction is as it was, and stays closed.
    assert (db.query(Agreement).filter(Agreement.project_id == p1).one().completed_at, db.query(Review).count()) == before
    assert a.get(f"/projects/{p1}").json()["status"] == "awarded"
    assert x.post(f"/projects/{p1}/agreement/completion/submit", json={}, headers=_v(x, p1)).status_code == 409


def test_endings_that_never_produce_a_review(db):
    # 4. Terminated: neither side may review.
    owner, a, b, pid, _wid, _ = _started(db)
    assert owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid)).status_code == 200
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 1}).status_code == 400
    assert a.post("/service-provider/reviews", json={"project_id": pid, "rating": 1}).status_code == 400
    assert b.post("/service-provider/reviews", json={"project_id": pid, "rating": 1}).status_code == 404  # 5. the loser
    # 3. Cancelled: nothing to review, nothing counted.
    p2 = _tender(owner, title="Cancelled")
    _submitted(a, p2)
    owner.post(f"/owner/projects/{p2}/close")
    owner.post(f"/owner/projects/{p2}/cancel", json={"reason": "other"})
    assert owner.post("/owner/reviews", json={"project_id": p2, "rating": 1}).status_code == 400
    assert a.post("/service-provider/reviews", json={"project_id": p2, "rating": 1}).status_code == 404
    assert db.query(Review).count() == 0
    assert (a.get("/service-provider/reputation").json()["completed_transactions"], owner.get("/owner/reputation").json()["completed_transactions"]) == (0, 0)
    assert a.get("/service-provider/previous-owners").json() == [] and owner.get("/owner/previous-providers").json() == []

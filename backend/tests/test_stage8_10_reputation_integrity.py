"""Stage 8.10: the review and reputation chain end to end -- completed
transaction -> one review per direction -> reputation -> one response --
held by the server against substitution, outsiders, former members, replays
and concurrency, with the provider's stored rating (shown on offers) always
equal to the live count."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app
from app.models.review import Review
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award


def _login(email):
    c = TestClient(app)
    c.post("/auth/login", json={"email": email, "password": "password123"})
    return c


def test_the_chain_end_to_end(db):
    a, a2, _, a2_id = _organization(db, "owner", "Owner A W.L.L.", "a@a.example", "a2@a.example")
    x, x2, x_id, _ = _organization(db, "service_provider", "X Contracting", "x@x.example", "x2@x.example")
    y = _account(db, "service_provider", "y@example.com", organization="Y Co")
    b = _account(db, "owner", "b@example.com")
    # 1-3. A awards X (Y loses); the work is completed and accepted.
    pid = _tender(a, title="Private works")
    _award(a, x2, pid, y)
    # Before completion: no review either way.
    assert a.post("/owner/reviews", json={"project_id": pid, "rating": 4}).status_code == 400
    assert x.post("/service-provider/reviews", json={"project_id": pid, "rating": 5}).status_code == 400
    complete_transaction(a, x2, pid)
    # 4-5. One review each way; ids in the request are ignored; replays are refused.
    forged = {"owner_id": b.get("/auth/me").json()["id"], "service_provider_id": y.get("/auth/me").json()["id"]}
    assert a2.post("/owner/reviews", json={"project_id": pid, "rating": 4, "comment": "Good.", **forged}).status_code == 200
    assert x.post("/service-provider/reviews", json={"project_id": pid, "rating": 5, "comment": "Fair owner.", **forged}).status_code == 200
    for client, path in ((a, "/owner/reviews"), (x2, "/service-provider/reviews")):
        assert client.post(path, json={"project_id": pid, "rating": 1}).status_code == 409
    for bad in (0, 6, 4.5, "5", None):
        assert a.post("/owner/reviews", json={"project_id": pid, "rating": bad}).status_code == 422
    rows = {r.direction: r for r in db.query(Review)}
    assert {(d, r.owner_id, r.service_provider_id) for d, r in rows.items()} == {
        ("owner_to_provider", rows["owner_to_provider"].owner_id, x_id), ("provider_to_owner", rows["owner_to_provider"].owner_id, x_id)}
    # 6. Both reputations, never swapped; the stored provider rating matches.
    xr, ar = x.get("/service-provider/reputation").json(), a.get("/owner/reputation").json()
    assert (xr["completed_transactions"], xr["review_count"], xr["avg_rating"]) == (1, 1, 4.0)
    assert (ar["completed_transactions"], ar["review_count"], ar["avg_rating"]) == (1, 1, 5.0)
    profile = db.get(ServiceProviderProfile, x_id)
    db.refresh(profile)
    assert (profile.review_count, float(profile.avg_rating)) == (1, 4.0)
    # 7-8. One response each way; ratings untouched.
    assert a.post(f"/owner/projects/{pid}/review/received/response", json={"response": "Thank you."}).status_code == 200
    assert x2.post(f"/service-provider/projects/{pid}/review/received/response", json={"response": "Thanks."}).status_code == 200
    assert (x.get("/service-provider/reputation").json()["avg_rating"], a.get("/owner/reputation").json()["avg_rating"]) == (4.0, 5.0)
    # 9-10, 13. Y (lost) and B (unrelated) can neither read nor write either side's review data.
    for path in ("review", "review/received"):
        assert y.get(f"/service-provider/projects/{pid}/{path}").status_code == 404
        assert b.get(f"/owner/projects/{pid}/{path}").status_code == 404
    assert y.post("/service-provider/reviews", json={"project_id": pid, "rating": 1}).status_code == 404
    assert y.post(f"/service-provider/projects/{pid}/review/received/response", json={"response": "x"}).status_code == 404
    assert b.post("/owner/reviews", json={"project_id": pid, "rating": 1}).status_code == 404
    assert b.post(f"/owner/projects/{pid}/review/received/response", json={"response": "x"}).status_code == 404
    # 15. Substituted ids: a review id, a party id, an organisation id are not project ids.
    rid = rows["owner_to_provider"].id
    for guess in (rid, x_id, a2_id):
        assert y.get(f"/service-provider/projects/{guess}/review/received").status_code == 404
        assert b.get(f"/projects/{guess}/owner-reputation").status_code == 404
    # 14. A former member can't act for the organisation any more.
    assert a.delete(f"/account/organization/members/{a2_id}").status_code == 200
    assert a2.post("/owner/reviews", json={"project_id": pid, "rating": 1}).status_code in (403, 404)
    assert a2.get(f"/owner/projects/{pid}/review/received").status_code == 404
    # 12. A cancelled requirement contributes nothing.
    p2 = _tender(a, title="Cancelled")
    _submitted(x, p2)
    a.post(f"/owner/projects/{p2}/close")
    a.post(f"/owner/projects/{p2}/cancel", json={"reason": "other"})
    assert a.post("/owner/reviews", json={"project_id": p2, "rating": 1}).status_code == 400
    # Final state: exactly two reviews, two responses, nothing leaked to the outsiders above.
    assert db.query(Review).count() == 2 and db.query(Review).filter(Review.response.isnot(None)).count() == 2
    assert (x.get("/service-provider/reputation").json()["completed_transactions"], a.get("/owner/reputation").json()["completed_transactions"]) == (1, 1)


@needs_mysql
def test_concurrent_reviews_keep_one_review_and_a_true_stored_rating(db):
    """11/12: several owners review the same provider at the same moment, each
    on its own transaction; and two members of one side review / respond at once."""
    x, x2, x_id, _ = _organization(db, "service_provider", "X Contracting", "x@x.example", "x2@x.example")
    owners, pids = [], []
    for i in range(4):
        o = _account(db, "owner", f"o{i}@example.com")
        p = _tender(o, title=f"Job {i}")
        _award(o, x, p)
        complete_transaction(o, x, p)
        owners.append(f"o{i}@example.com")
        pids.append(p)
    with ThreadPoolExecutor(4) as pool:
        codes = [f.result().status_code for f in [
            pool.submit(lambda e=e, p=p, r=r: _login(e).post("/owner/reviews", json={"project_id": p, "rating": r}))
            for e, p, r in zip(owners, pids, (5, 4, 3, 2))]]
    assert codes == [200] * 4, codes
    db.expire_all()
    profile = db.get(ServiceProviderProfile, x_id)
    assert (profile.review_count, float(profile.avg_rating)) == (4, 3.5)  # the stored rating owners see on offers
    live = x.get("/service-provider/reputation").json()
    assert (live["review_count"], live["avg_rating"]) == (4, 3.5)
    # The same side twice at once: one review, then one response.
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(f.result().status_code for f in [
            pool.submit(lambda e=e: _login(e).post("/service-provider/reviews", json={"project_id": pids[0], "rating": 5})) for e in ("x@x.example", "x2@x.example")])
    assert codes == [200, 409], codes
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(f.result().status_code for f in [
            pool.submit(lambda e=e: _login(e).post(f"/service-provider/projects/{pids[0]}/review/received/response", json={"response": e}))
            for e in ("x@x.example", "x2@x.example")])
    assert codes == [200, 409], codes
    db.expire_all()
    assert db.query(Review).filter(Review.project_id == pids[0]).count() == 2
    assert db.query(Review).filter(Review.response.isnot(None)).count() == 1

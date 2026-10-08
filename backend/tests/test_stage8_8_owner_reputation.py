"""Stage 8.8: an owner's reputation is read live from Stage 7's completed
transactions on its requirements and the provider reviews on them -- the
organisation's, never an employee's; cancelled or unfinished work and the
owner's own reviews of providers don't count. A provider weighing one of its
requirements sees counts and average only (the owner is anonymous to it
before an award, Stage 7.2); the owner side and admin also see the reviews."""
from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from app.models.owner import OwnerProfile
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award


def test_owner_reputation_follows_completed_work_and_provider_reviews_only(db):
    owner, noura, owner_id, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    x = _account(db, "service_provider", "x@example.com", organization="X Co")
    y = _account(db, "service_provider", "y@example.com", organization="Y Co")
    b = _account(db, "service_provider", "b@example.com", organization="B Co")
    mine = lambda: owner.get("/owner/reputation").json()  # noqa: E731

    # 1. Zero history.
    assert mine() == {"completed_transactions": 0, "review_count": 0, "avg_rating": None, "recent_reviews": []}

    # 2-4. Completed with X; X reviews 4/5. Awarded alone doesn't count; the owner's own review of X doesn't either.
    p1 = _tender(owner, title="Tower maintenance")
    _award(owner, x, p1, b)
    assert mine()["completed_transactions"] == 0
    complete_transaction(owner, x, p1)
    assert owner.post("/owner/reviews", json={"project_id": p1, "rating": 1}).status_code == 200
    assert x.post("/service-provider/reviews", json={"project_id": p1, "rating": 4, "comment": "Fair, clear scope."}).status_code == 200
    r = mine()
    assert (r["completed_transactions"], r["review_count"], r["avg_rating"]) == (1, 1, 4.0)

    # 5-7. Completed with Y (raised by a colleague -- it is still the organisation's); Y reviews 5/5.
    p2 = _tender(noura, title="Warehouse roof")
    _award(noura, y, p2)
    complete_transaction(noura, y, p2)
    assert y.post("/service-provider/reviews", json={"project_id": p2, "rating": 5, "comment": "Paid promptly."}).status_code == 200
    r = mine()
    assert (r["completed_transactions"], r["review_count"], r["avg_rating"]) == (2, 2, 4.5)
    assert sorted(x["rating"] for x in r["recent_reviews"]) == [4, 5]
    assert all(set(x) == {"rating", "comment", "created_at"} for x in r["recent_reviews"])

    # 8-9. A cancelled requirement and an unfinished award add nothing; a non-participant's review and a replay are refused.
    p3 = _tender(owner, title="Cancelled job")
    _submitted(x, p3)
    owner.post(f"/owner/projects/{p3}/close")
    owner.post(f"/owner/projects/{p3}/cancel", json={"reason": "other"})
    p4 = _tender(owner, title="Unfinished job")
    _award(owner, y, p4)
    assert b.post("/service-provider/reviews", json={"project_id": p1, "rating": 1}).status_code == 404
    assert x.post("/service-provider/reviews", json={"project_id": p1, "rating": 1}).status_code == 409
    assert y.post("/service-provider/reviews", json={"project_id": p4, "rating": 1}).status_code == 400
    # 10. Nothing in the request chooses whose reputation is read or what it holds.
    assert owner.get(f"/owner/reputation?owner_id={x.get('/auth/me').json()['id']}&avg_rating=1").json() == mine()
    assert (mine()["completed_transactions"], mine()["review_count"], mine()["avg_rating"]) == (2, 2, 4.5)

    # 11. Provider B, weighing a new requirement: counts and average only -- no review text, no owner identity.
    p5 = _tender(owner, title="New tender")
    seen = b.get(f"/projects/{p5}/owner-reputation")
    assert seen.json() == {"completed_transactions": 2, "review_count": 2, "avg_rating": 4.5, "recent_reviews": []}
    for private in ("Gulf Holdings", "Fair, clear scope.", "Tower maintenance", p1):
        assert private not in seen.text
    # The owner side on its own requirement, and admin, see the reviews too.
    assert len(noura.get(f"/projects/{p5}/owner-reputation").json()["recent_reviews"]) == 2
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    admin = TestClient(app)
    admin.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    assert len(admin.get(f"/projects/{p5}/owner-reputation").json()["recent_reviews"]) == 2
    # Who may not: a provider on a requirement it can't open (closed, not its bid), another owner, no session.
    other = _account(db, "owner", "other@example.com")
    assert b.get(f"/projects/{p3}/owner-reputation").status_code == 404
    assert other.get(f"/projects/{p5}/owner-reputation").status_code == 404
    assert TestClient(app).get(f"/projects/{p5}/owner-reputation").status_code == 401
    assert TestClient(app).get("/owner/reputation").status_code == 401
    assert x.get("/owner/reputation").status_code == 403
    assert other.get("/owner/reputation").json()["completed_transactions"] == 0

    # 12. The reputation stays with the organisation: a member who leaves takes none of it.
    db.get(OwnerProfile, owner_id).verification_note = "unrelated profile change"
    db.commit()
    assert owner.delete(f"/account/organization/members/{noura_id}").status_code == 200
    assert mine()["completed_transactions"] == 2
    left = noura.get("/owner/reputation")
    assert left.status_code == 404 or (left.json()["completed_transactions"], left.json()["review_count"]) == (0, 0)

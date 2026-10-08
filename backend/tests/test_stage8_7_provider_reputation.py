"""Stage 8.7: a provider's reputation is read live from Stage 7's completed
transactions and the owner reviews on them -- the organisation's, never an
employee's; cancelled, lost or unfinished work and the provider's own reviews
of owners don't count; owners see it only for an offer they may already read;
nothing is taken from the request; no transaction detail leaks."""
from fastapi.testclient import TestClient

from app.main import app
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender


def _award(owner, winner, pid, *others):
    _submitted(winner, pid)
    for o in others:
        _submitted(o, pid)
    owner.post(f"/owner/projects/{pid}/close")
    offer_id = winner.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve").status_code == 200
    return offer_id


def test_reputation_follows_completed_work_and_owner_reviews_only(db):
    owner, _, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, amal_id, sami_id = _organization(db, "service_provider", "Amal Contracting", "amal@amal.example", "sami@amal.example")
    rival = _account(db, "service_provider", "rival@example.com", organization="Rival Co")
    mine = lambda: amal.get("/service-provider/reputation").json()  # noqa: E731

    # 1. Zero history: "none yet", not a 0 rating.
    assert mine() == {"company_name": "Amal Contracting", "completed_transactions": 0, "review_count": 0, "avg_rating": None, "recent_reviews": []}

    # 2-4. First transaction: awarded is not completed; completed counts; a 4/5 owner review.
    p1 = _tender(owner, title="Tower maintenance")
    _award(owner, sami, p1, rival)
    assert mine()["completed_transactions"] == 0
    complete_transaction(owner, sami, p1)
    assert (mine()["completed_transactions"], mine()["review_count"]) == (1, 0)
    assert owner.post("/owner/reviews", json={"project_id": p1, "rating": 4, "comment": "Solid work."}).status_code == 200
    # The provider's review of the owner doesn't touch its own reputation; a duplicate isn't counted.
    assert sami.post("/service-provider/reviews", json={"project_id": p1, "rating": 1}).status_code == 200
    assert owner.post("/owner/reviews", json={"project_id": p1, "rating": 1}).status_code == 409
    r = mine()
    assert (r["completed_transactions"], r["review_count"], r["avg_rating"]) == (1, 1, 4.0)

    # 5-7. Second transaction, 5/5: the simple average of two.
    p2 = _tender(owner, title="Warehouse roof")
    _award(owner, amal, p2)
    complete_transaction(owner, amal, p2)
    assert owner.post("/owner/reviews", json={"project_id": p2, "rating": 5, "comment": "Excellent."}).status_code == 200
    r = mine()
    assert (r["completed_transactions"], r["review_count"], r["avg_rating"]) == (2, 2, 4.5)
    assert [(x["rating"], x["comment"]) for x in r["recent_reviews"]] in ([(5, "Excellent."), (4, "Solid work.")], [(4, "Solid work."), (5, "Excellent.")])
    assert all(set(x) == {"rating", "comment", "created_at"} for x in r["recent_reviews"])

    # 8-9. A cancelled requirement, a lost tender and an awarded-but-unfinished one add nothing.
    p3 = _tender(owner, title="Cancelled job")
    _submitted(sami, p3)
    owner.post(f"/owner/projects/{p3}/close")
    owner.post(f"/owner/projects/{p3}/cancel", json={"reason": "other"})
    p4 = _tender(owner, title="Lost job")
    _award(owner, rival, p4, sami)
    complete_transaction(owner, rival, p4)
    p5 = _tender(owner, title="Unfinished job")
    _award(owner, sami, p5)
    assert (mine()["completed_transactions"], mine()["review_count"]) == (2, 2)
    assert rival.get("/service-provider/reputation").json()["completed_transactions"] == 1  # the work it did is its own

    # The organisation keeps its reputation; a member who leaves takes none of it.
    assert sami.get("/service-provider/reputation").json() == mine()
    db.get(ServiceProviderProfile, amal_id).company_name = "Amal Contracting & Sons"
    db.commit()
    assert amal.delete(f"/account/organization/members/{sami_id}").status_code == 200
    assert mine()["completed_transactions"] == 2 and mine()["company_name"] == "Amal Contracting & Sons"
    left = sami.get("/service-provider/reputation")
    assert left.status_code == 404 or left.json()["completed_transactions"] == 0

    # 11. Nothing in the request chooses whose reputation is read or what it holds.
    assert amal.get(f"/service-provider/reputation?service_provider_id={rival.get('/auth/me').json()['id']}&avg_rating=5").json() == mine()

    # An owner weighing Amal's offer on a new tender sees the same record -- once
    # it may read the offer -- and nothing of the earlier transactions.
    other = _account(db, "owner", "other@example.com")
    p6 = _tender(other, title="New tender", sealed=True)
    _submitted(amal, p6)
    offer6 = amal.get(f"/projects/{p6}/offers/mine").json()["id"]
    assert other.get(f"/owner/projects/{p6}/offers/{offer6}/reputation").status_code == 404  # sealed and open
    p7 = _tender(other, title="Open tender")
    _submitted(amal, p7)
    offer7 = amal.get(f"/projects/{p7}/offers/mine").json()["id"]
    seen = other.get(f"/owner/projects/{p7}/offers/{offer7}/reputation")
    assert seen.json() == mine()
    for private in ("Tower maintenance", "Warehouse roof", "Gulf Holdings", p1, p2, "amount"):
        assert private not in seen.text
    # Substituted ids lead nowhere: another owner's project, an offer from another project, the wrong role, no session.
    assert owner.get(f"/owner/projects/{p7}/offers/{offer7}/reputation").status_code == 404
    assert other.get(f"/owner/projects/{p7}/offers/{offer6}/reputation").status_code == 404
    assert rival.get(f"/owner/projects/{p7}/offers/{offer7}/reputation").status_code == 403
    assert TestClient(app).get("/service-provider/reputation").status_code == 401
    assert TestClient(app).get(f"/owner/projects/{p7}/offers/{offer7}/reputation").status_code == 401

    # Reputation is informational: the stored profile's verification and standing are untouched.
    profile = db.get(ServiceProviderProfile, amal_id)
    db.refresh(profile)
    assert (profile.verification_status.value, profile.is_suspended) == ("approved", False)

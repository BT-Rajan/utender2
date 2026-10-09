"""Stage 8.14: while an owner weighs offers, each provider's track record
(completed transactions, owner reviews with their count, work done with this
owner) appears beside the offer -- the same authoritative figures as
everywhere else, never while sealed, and never changing which offers are
shown, their order, eligibility or award. A new provider reads as
"none yet"; outsiders see nothing."""
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award


def _history(owner, provider, title, rating):
    pid = _tender(owner, title=title)
    _award(owner, provider, pid)
    complete_transaction(owner, provider, pid)
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": rating}).status_code == 200


def _signals(o):
    return (o["service_provider_completed_transactions"], o["service_provider_review_count"],
            float(o["service_provider_avg_rating"]) if o["service_provider_review_count"] else None, o["completed_with_you"])


def test_trust_signals_inform_without_ranking(db):
    a = _account(db, "owner", "a@example.com")
    o1 = _account(db, "owner", "o1@example.com")
    x = _account(db, "service_provider", "x@example.com", organization="X Co")
    y = _account(db, "service_provider", "y@example.com", organization="Y Co")
    z = _account(db, "service_provider", "z@example.com", organization="Z Co")
    _history(a, x, "Earlier with A", 4)
    _history(o1, x, "Earlier with O1", 5)
    _history(o1, y, "Y's job", 5)

    # 1-3. R: Z, Y and X bid (in that order); the owner opens the inbox.
    r = _tender(a, title="New requirement")
    for p in (z, y, x):
        _submitted(p, r)
    a.post(f"/owner/projects/{r}/close")
    offers = a.get(f"/owner/projects/{r}/offers").json()
    by = {o["service_provider_id"]: o for o in offers}
    ids = {name: p.get("/auth/me").json()["id"] for name, p in (("x", x), ("y", y), ("z", z))}
    # 4-6. Honest figures: X 2 completed, 2 reviews at 4.5, once with A; Y 1 at 5.0; Z none.
    assert _signals(by[ids["x"]]) == (2, 2, 4.5, 1)
    assert _signals(by[ids["y"]]) == (1, 1, 5.0, 0)
    assert _signals(by[ids["z"]]) == (0, 0, None, 0)
    # 7-10. The order is the inbox's own (submission, then id) -- not reputation.
    assert [o["id"] for o in offers] == [o["id"] for o in sorted(offers, key=lambda o: (o["submitted_at"], o["id"]))]
    # Consistent with every other view of the same provider.
    for name, p in (("x", x), ("y", y), ("z", z)):
        own = p.get("/service-provider/reputation").json()
        seen = a.get(f"/owner/projects/{r}/offers/{by[ids[name]]['id']}/reputation").json()
        assert (own["completed_transactions"], own["review_count"], own["avg_rating"]) == (
            seen["completed_transactions"], seen["review_count"], seen["avg_rating"]) == _signals(by[ids[name]])[:3]
        assert seen["completed_with_you"] == by[ids[name]]["completed_with_you"]
    # The comparison: the same figures, in the order the owner chose.
    chosen = [by[ids[n]]["id"] for n in ("z", "x", "y")]
    cmp = a.get(f"/owner/projects/{r}/offers/compare", params=[("ids", i) for i in chosen]).json()
    assert [o["id"] for o in cmp["offers"]] == chosen
    assert [_signals(o) for o in cmp["offers"]] == [_signals(by[ids[n]]) for n in ("z", "x", "y")]
    # Nothing in the request changes them.
    tampered = a.get(f"/owner/projects/{r}/offers?service_provider_completed_transactions=99&completed_with_you=5&owner_id={ids['x']}").json()
    assert [_signals(o) for o in tampered] == [_signals(o) for o in offers]

    # 13 / 10-11. The owner decides: the new provider can be awarded like anyone.
    assert a.post(f"/owner/projects/{r}/offers/{by[ids['z']]['id']}/approve").status_code == 200

    # 12. Eligibility stays authoritative: X's history doesn't let a suspended X bid.
    db.get(ServiceProviderProfile, ids["x"]).is_suspended = True
    db.commit()
    r2 = _tender(a, title="Another")
    assert x.post(f"/projects/{r2}/offers", json={"amount": "100"}).status_code == 403
    db.get(ServiceProviderProfile, ids["x"]).is_suspended = False
    db.commit()

    # 14-15. Privacy: nothing while sealed; nothing for another owner or a provider; owners stay anonymous.
    sealed = _tender(a, title="Sealed", sealed=True)
    _submitted(x, sealed)
    assert [_signals(o) for o in a.get(f"/owner/projects/{sealed}/offers").json()] == [(None, None, None, None)]
    assert o1.get(f"/owner/projects/{r}/offers").status_code == 404
    assert o1.get(f"/owner/projects/{r}/offers/compare", params=[("ids", i) for i in chosen]).status_code == 404
    assert x.get(f"/owner/projects/{r}/offers").status_code == 403
    assert x.get(f"/projects/{r2}/owner-reputation").json()["recent_reviews"] == []

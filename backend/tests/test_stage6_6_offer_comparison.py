"""Stage 6.6: offer comparison. The owner puts chosen offers on their own
requirement side by side -- each exactly as stored, in the order chosen,
never scored or ranked; only live offers they may review on that
requirement; nothing for anyone else."""
from datetime import datetime, timedelta

from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import REV2, _submitted, _tender


def _compare(client, pid, ids):
    return client.get(f"/owner/projects/{pid}/offers/compare", params=[("ids", i) for i in ids])


def _ids(db, pid):
    return {o.service_provider_id: o.id for o in db.query(Offer).filter(Offer.project_id == pid)}


def test_chosen_offers_side_by_side_as_stored_in_the_order_chosen(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana"))
    pid = _tender(owner)
    for sp in (a, b, c):
        _submitted(sp, pid)
    assert b.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}).status_code == 200  # cheaper now
    by_name = {o["service_provider_company_name"]: o["id"] for o in owner.get(f"/owner/projects/{pid}/offers").json()}
    chosen = [by_name["dana"], by_name["badr"], by_name["dana"]]  # a repeat counts once
    r = _compare(owner, pid, chosen)
    assert r.status_code == 200, r.text
    d = r.json()
    # The order chosen, not by price: no ranking.
    assert [o["service_provider_company_name"] for o in d["offers"]] == ["dana", "badr"]
    assert d["unavailable"] == [] and d["requirement"]["id"] == pid
    # Each exactly as stored: the current (revised) version, never an earlier one alongside it.
    badr = next(o for o in d["offers"] if o["service_provider_company_name"] == "badr")
    stored = db.get(Offer, by_name["badr"])
    assert (badr["amount"], badr["message"], badr["revision"], badr["proposed_duration_days"]) == ("900.000", "Method v2", 2, stored.proposed_duration_days)
    assert all(o["documents"] and o["documents"][0]["url"].startswith("http") for o in d["offers"])
    # Nothing in it scores, ranks or recommends.
    assert not any(k in r.text.lower() for k in ("score", "rank", "recommend", "best", "winner"))
    # Reading it changed nothing.
    db.expire_all()
    assert db.get(Offer, by_name["badr"]).amount == stored.amount


def test_only_live_offers_on_this_requirement_and_only_for_its_owner(db):
    owner = _account(db, "owner", "owner@example.com")
    stranger = _account(db, "owner", "stranger@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana"))
    pid, other, sealed = _tender(owner, "Here"), _tender(owner, "Elsewhere"), _tender(owner, "Sealed", sealed=True)
    for sp in (a, b, c):
        _submitted(sp, pid)
    _submitted(a, other)
    _submitted(a, sealed)
    _submitted(b, sealed)
    here = list(_ids(db, pid).values())
    elsewhere = list(_ids(db, other).values())
    # An offer from another requirement is never mixed in.
    d = _compare(owner, pid, here[:2] + elsewhere).json()
    assert [o["id"] for o in d["offers"]] == here[:2] and d["unavailable"] == elsewhere
    # A withdrawn offer drops out (even mid-comparison), as does a suspended one.
    a_offer = _ids(db, pid)[a.get("/auth/me").json()["id"]]
    assert a.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    c_offer = _ids(db, pid)[c.get("/auth/me").json()["id"]]
    db.get(Offer, c_offer).is_suspended = True
    db.commit()
    d = _compare(owner, pid, here).json()
    assert a_offer in d["unavailable"] and c_offer in d["unavailable"] and len(d["offers"]) == 1
    # Not the owner, a provider (even one of the bidders), a sealed tender: nothing.
    assert _compare(stranger, pid, here).status_code == 404
    assert _compare(b, pid, here).status_code == 403
    sealed_ids = list(_ids(db, sealed).values())
    assert _compare(owner, sealed, sealed_ids).status_code == 404
    db.get(Project, sealed).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert len(_compare(owner, sealed, sealed_ids).json()["offers"]) == 2
    # Bounded; at least one id.
    assert _compare(owner, pid, [f"x{i}" for i in range(11)]).status_code == 400
    assert owner.get(f"/owner/projects/{pid}/offers/compare").status_code == 422


def test_versions_stay_visible_across_an_amendment_and_closing(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    _submitted(a, pid)
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Substation plus a second bay."}, headers={"If-Match": str(v)})
    _submitted(b, pid)
    ids = list(_ids(db, pid).values())
    d = _compare(owner, pid, ids).json()
    assert sorted(o["based_on_material_revision"] for o in d["offers"]) == [0, 1] and d["requirement"]["material_revision"] == 1
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    assert sorted(o["based_on_material_revision"] for o in _compare(owner, pid, ids).json()["offers"]) == [0, 1]

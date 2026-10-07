"""Stage 6.3: offer completeness & status, as the owner sees it. Only offers
that passed the Stage 5 submission checks reach the owner; each shows its
persisted status, version and the requirement version it answered; one offer
per provider however often it is revised; counts agree everywhere."""
from app.models.offer import Offer
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import DECL, REV2, _submitted, _tender


def _inbox(owner, pid):
    return {o["service_provider_company_name"]: o for o in owner.get(f"/owner/projects/{pid}/offers").json()}


def test_only_complete_submissions_reach_the_owner(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)  # asks for a technical response, a method statement and a declaration
    sp.post(f"/projects/{pid}/participate")
    sp.put(f"/projects/{pid}/offers/draft", json={"amount": "1000", "accepted_declarations": [DECL]})
    # Incomplete (no technical response, no required document): refused, and nothing reaches the owner.
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code in (400, 422), r.text
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    assert owner.get(f"/projects/{pid}").json()["offer_count"] == 0
    assert db.query(Offer).one().status.value == "draft"


def test_status_version_and_counts_follow_the_persisted_offer(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana"))
    pid = _tender(owner)
    for sp in (a, b, c):
        _submitted(sp, pid)
    first = _inbox(owner, pid)
    assert {n: (o["status"], o["revision"]) for n, o in first.items()} == {"amal": ("submitted", 1), "badr": ("submitted", 1), "dana": ("submitted", 1)}

    # While the owner has the page open: A revises, B withdraws. The next read shows exactly that.
    assert a.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}).status_code == 200
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    now = _inbox(owner, pid)
    assert len(now) == 3  # one offer per provider, however often revised
    assert (now["amal"]["status"], now["amal"]["revision"], now["amal"]["amount"]) == ("submitted", 2, "900.000")
    assert now["amal"]["submitted_at"] == first["amal"]["submitted_at"]  # first submitted; the revision is its update
    assert now["badr"]["status"] == "withdrawn" and now["badr"]["amount"] is None
    # The owner's older view of B's offer can't be acted on: B's offer is not a live one.
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/offers/{first['badr']['id']}/approve").status_code == 400
    # Its earlier versions stay on record, for the owner once readable.
    assert [h["revision_number"] for h in owner.get(f"/owner/projects/{pid}/offers/{now['amal']['id']}/history").json()] == [1]

    # An admin-suspended offer is out of the inbox, and out of every count the owner sees.
    db.query(Offer).filter(Offer.id == now["dana"]["id"]).one().is_suspended = True
    db.commit()
    assert set(_inbox(owner, pid)) == {"amal", "badr"}
    assert owner.get(f"/projects/{pid}").json()["offer_count"] == 2
    assert next(p for p in owner.get("/owner/projects").json() if p["id"] == pid)["offer_count"] == 2


def test_an_amendment_never_makes_an_old_offer_look_current(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"description": "Substation plus a second bay."}, headers={"If-Match": str(v)}).status_code == 200
    assert owner.get(f"/projects/{pid}").json()["material_revision"] == 1
    # Both still answered version 0 until their provider acts.
    assert {n: o["based_on_material_revision"] for n, o in _inbox(owner, pid).items()} == {"amal": 0, "badr": 0}
    assert a.post(f"/projects/{pid}/offers/confirm").status_code == 200
    seen = _inbox(owner, pid)
    assert (seen["amal"]["based_on_material_revision"], seen["badr"]["based_on_material_revision"]) == (1, 0)
    # The trail keeps that A first answered version 0.
    assert [h["based_on_material_revision"] for h in owner.get(f"/owner/projects/{pid}/offers/{seen['amal']['id']}/history").json()] == [0]

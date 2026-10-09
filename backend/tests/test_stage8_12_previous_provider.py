"""Stage 8.12: an owner organisation recognises the providers it completed
U-Tender work with -- from Stage 7 completion only, organisation to
organisation -- beside their offers and in its own history. It is
information: offers keep their order, nobody is awarded or made eligible by
it, and nobody else can learn of the relationship."""
from app.models.award_record import AwardRecord
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award


def _mine(client, pid):
    return client.get(f"/projects/{pid}/offers/mine").json()["id"]


def test_previous_providers_come_from_completed_work_only(db):
    owner, noura, _, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, x_id, _ = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    y = _account(db, "service_provider", "y@example.com", organization="Y Co")
    z = _account(db, "service_provider", "z@example.com", organization="Z Co")
    other = _account(db, "owner", "b@example.com")
    prev = lambda c=owner: c.get("/owner/previous-providers").json()  # noqa: E731

    # 1-5. R1: X (submitted by one member) wins over Y; not "previous" until completed.
    r1 = _tender(owner, title="Painting 2025")
    _award(owner, sami, r1, y)
    assert prev() == []
    complete_transaction(owner, sami, r1)
    # 14. A cancelled tender and an unfinished award add nobody.
    r0 = _tender(owner, title="Cancelled")
    _submitted(z, r0)
    owner.post(f"/owner/projects/{r0}/close")
    owner.post(f"/owner/projects/{r0}/cancel", json={"reason": "other"})
    _award(owner, z, _tender(owner, title="Unfinished"))
    # 6. X once, as the organisation, with that requirement; Y (lost) and Z (cancelled/unfinished) absent.
    p = prev()
    assert [(e["company_name"], e["completed_transactions"], [t["title"] for t in e["transactions"]]) for e in p] == [("X Contracting", 1, ["Painting 2025"])]
    assert noura.get("/owner/previous-providers").json() == p  # every member of the organisation

    # 7-10. R2, raised by a colleague: X is recognised beside its offer; Y competes as usual; nobody is awarded.
    r2 = _tender(noura, title="Painting 2026")
    _submitted(y, r2)
    _submitted(amal, r2)
    owner.post(f"/owner/projects/{r2}/close")
    offers = owner.get(f"/owner/projects/{r2}/offers").json()
    assert {(o["service_provider_company_name"], o["completed_with_you"]) for o in offers} == {("y", 0), ("X Contracting", 1)}
    assert [o["id"] for o in offers] == [o["id"] for o in owner.get(f"/owner/projects/{r2}/offers").json()]  # the usual order, unaffected
    assert db.query(AwardRecord).filter(AwardRecord.project_id == r2).count() == 0
    rep = owner.get(f"/owner/projects/{r2}/offers/{_mine(amal, r2)}/reputation").json()
    assert rep["completed_with_you"] == 1 and rep["completed_transactions"] == 1
    # Another completion with X: one relationship, two transactions.
    owner.post(f"/owner/projects/{r2}/offers/{_mine(amal, r2)}/approve")
    complete_transaction(owner, amal, r2)
    assert [(e["completed_transactions"], len(e["transactions"])) for e in prev()] == [(2, 2)]

    # A sealed tender still open says nothing about who bid.
    r3 = _tender(owner, title="Sealed", sealed=True)
    _submitted(amal, r3)
    assert [o["completed_with_you"] for o in owner.get(f"/owner/projects/{r3}/offers").json()] == [None]

    # 12. Nobody else learns of it: another owner, a provider, by id or otherwise.
    assert prev(other) == []
    assert other.get(f"/owner/projects/{r2}/offers/{_mine(amal, r2)}/reputation").status_code == 404
    assert amal.get("/owner/previous-providers").status_code == 403
    assert "completed_with_you" not in str(amal.get("/service-provider/reputation").json()) or amal.get("/service-provider/reputation").json()["completed_with_you"] is None
    # 13. X still sees its own history.
    assert {r1, r2} <= {b["project_id"] for b in amal.get("/service-provider/my-bids").json()}

    # 11. Eligibility stays authoritative: a suspended X can't bid, though the history stays.
    profile = db.get(ServiceProviderProfile, x_id)
    profile.is_suspended = True
    db.commit()
    r4 = _tender(owner, title="Painting 2027")
    assert amal.post(f"/projects/{r4}/offers", json={"amount": "100"}).status_code == 403
    assert prev()[0]["completed_transactions"] == 2
    profile.is_suspended = False
    db.commit()

    # 8.11 reuse of R1 copies no provider, offer or award.
    r5 = owner.post(f"/owner/projects/{r1}/restart").json()["id"]
    assert owner.get(f"/owner/projects/{r5}/offers").json() == []
    assert db.query(AwardRecord).filter(AwardRecord.project_id == r5).count() == 0

    # Member changes don't move the relationship.
    assert owner.delete(f"/account/organization/members/{noura_id}").status_code == 200
    assert prev()[0]["completed_transactions"] == 2
    left = noura.get("/owner/previous-providers")
    assert left.status_code == 404 or left.json() == []

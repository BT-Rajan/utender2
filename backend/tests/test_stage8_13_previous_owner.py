"""Stage 8.13: a provider organisation recognises the owners it completed
U-Tender work for -- from Stage 7 completion only, organisation to
organisation, by name only. Their new requirements reach it through the
normal feed and eligibility, unlabelled (the owner is named on award, 7.2):
no advantage, no contact channel, nothing private."""
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award


def test_previous_owners_come_from_completed_work_only(db):
    owner, noura, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, x_id, sami_id = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    y = _account(db, "service_provider", "y@example.com", organization="Y Co")
    b = _account(db, "owner", "b@example.com")  # an individual owner
    prev = lambda c=amal: c.get("/service-provider/previous-owners").json()  # noqa: E731

    # 1-5. R1 awarded to X (Y loses); nothing until completed.
    r1 = _tender(owner, title="Painting 2025")
    _award(owner, sami, r1, y)
    assert prev() == []
    complete_transaction(owner, sami, r1)
    # 14 / 13. Owner B: X lost one, one was cancelled, one is unfinished -- B is no previous customer of X.
    lost = _tender(b, title="Lost")
    _award(b, y, lost, amal)
    complete_transaction(b, y, lost)
    cancelled = _tender(b, title="Cancelled")
    _submitted(amal, cancelled)
    b.post(f"/owner/projects/{cancelled}/close")
    b.post(f"/owner/projects/{cancelled}/cancel", json={"reason": "other"})
    _award(b, amal, _tender(b, title="Unfinished"))
    # 6. Owner A, once, as the organisation; for every member of X.
    p = prev()
    assert [(e["owner_name"], e["completed_transactions"], [t["title"] for t in e["transactions"]]) for e in p] == [("Gulf Holdings W.L.L.", 1, ["Painting 2025"])]
    assert prev(sami) == p
    assert "@" not in amal.get("/service-provider/previous-owners").text  # names only, never contact details
    # Y's history is its own: B (completed), not A (lost).
    assert [e["completed_transactions"] for e in prev(y)] == [1] and "Gulf" not in str(prev(y))

    # 7-10. R2 (from a colleague) reaches X and Y alike through the normal feed, unlabelled.
    r2 = _tender(noura, title="Painting 2026")
    feeds = {name: c.get("/service-provider/feed").json()["items"] for name, c in (("x", amal), ("y", y))}
    for name, feed in feeds.items():
        item = next(i for i in feed if i["id"] == r2)
        assert "Gulf" not in str(item) and "previous" not in str(item).lower(), name
    assert amal.get(f"/projects/{r2}").json().get("owner_name") is None
    _submitted(amal, r2)
    _submitted(y, r2)
    assert owner.get(f"/projects/{r2}").json()["status"] == "open"  # no automatic award

    # Multiple completions: one owner entry, the transactions listed.
    owner.post(f"/owner/projects/{r2}/close")
    owner.post(f"/owner/projects/{r2}/offers/{amal.get(f'/projects/{r2}/offers/mine').json()['id']}/approve")
    complete_transaction(owner, amal, r2)
    assert [(e["completed_transactions"], len(e["transactions"])) for e in prev()] == [(2, 2)]

    # 11-12. Eligibility stays authoritative; history stays readable; nothing private opens.
    profile = db.get(ServiceProviderProfile, x_id)
    profile.is_suspended = True
    db.commit()
    r3 = _tender(owner, title="Painting 2027")
    assert amal.get("/service-provider/feed").status_code == 403
    assert amal.post(f"/projects/{r3}/offers", json={"amount": "100"}).status_code == 403
    assert prev()[0]["completed_transactions"] == 2
    profile.is_suspended = False
    db.commit()
    draft = owner.post(f"/owner/projects/{r1}/restart").json()["id"]  # 8.11: a new draft, private until published
    assert amal.get(f"/projects/{draft}").status_code == 404
    assert amal.get(f"/owner/projects/{r1}/offers").status_code == 403
    assert owner.get("/service-provider/previous-owners").status_code == 403

    # Member changes don't move the relationship.
    assert amal.delete(f"/account/organization/members/{sami_id}").status_code == 200
    assert prev()[0]["completed_transactions"] == 2
    left = sami.get("/service-provider/previous-owners")
    assert left.status_code == 404 or left.json() == []

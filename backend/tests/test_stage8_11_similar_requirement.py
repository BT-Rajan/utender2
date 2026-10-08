"""Stage 8.11: after a completed transaction the owner side starts a similar
requirement -- the existing restart: a NEW draft with the old one's content
(description, items, rules, eligibility, fresh copies of its current files)
and nothing of its state, dates, offers, award, transaction or reviews. The
old requirement stays exactly as it was; the new one runs its own course."""
from app.models.agreement import Agreement
from app.models.project import Project
from app.models.review import Review
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award


def _file(client, doc):
    return client.get("/" + doc["url"].split("://", 1)[-1].split("/", 1)[-1])


def test_a_completed_requirement_starts_an_independent_similar_one(db):
    owner, noura, _, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    x = _account(db, "service_provider", "x@example.com", organization="X Co")
    y = _account(db, "service_provider", "y@example.com", organization="Y Co")
    a = _tender(owner, title="Office Building Painting - 2025")
    owner.post(f"/projects/{a}/drawings", files=[("drawings", ("site.pdf", b"%PDF-site", "application/pdf"))])
    _award(owner, x, a, y)
    # Awarded but unfinished: not yet.
    assert owner.post(f"/owner/projects/{a}/restart").status_code == 400
    complete_transaction(owner, x, a)
    assert owner.post("/owner/reviews", json={"project_id": a, "rating": 4}).status_code == 200
    assert x.post("/service-provider/reviews", json={"project_id": a, "rating": 5}).status_code == 200
    old = owner.get(f"/projects/{a}").json()

    # Only the owner organisation may: not another owner, a provider, or no session.
    other = _account(db, "owner", "other@example.com")
    assert other.post(f"/owner/projects/{a}/restart").status_code == 404
    assert x.post(f"/owner/projects/{a}/restart").status_code == 403

    # 2-4. A colleague creates the similar requirement: a new draft with a new identity.
    r = noura.post(f"/owner/projects/{a}/restart", json={"creation_token": "similar-1"})
    assert r.status_code == 201, r.text
    b = r.json()["id"]
    assert b != a and r.json()["status"] == "draft" and r.json()["offer_count"] == 0 and r.json()["restarted_from_id"] == a
    assert noura.post(f"/owner/projects/{a}/restart", json={"creation_token": "similar-1"}).json()["id"] == b  # a retry: the same draft
    draft = owner.get(f"/projects/{b}").json()
    assert draft["title"] == old["title"] and draft["description"] == old["description"]
    assert draft["bid_deadline"] != old["bid_deadline"] and draft["published_at"] is None
    # Nothing of A's transaction came along.
    assert owner.get(f"/owner/projects/{b}/offers").json() == []
    assert owner.get(f"/projects/{b}/agreement").status_code == 404
    assert owner.get(f"/owner/projects/{b}/review").json() is None
    assert db.query(Agreement).filter(Agreement.project_id == b).count() == 0
    assert db.query(Review).filter(Review.project_id == b).count() == 0
    # 14. The file is an independent copy: removing it from B leaves A's intact.
    new_doc, old_doc = draft["drawings"][0], old["drawings"][0]
    assert new_doc["id"] != old_doc["id"] and _file(owner, new_doc).content == b"%PDF-site"
    assert owner.delete(f"/projects/{b}/drawings/{new_doc['id']}").status_code == 200
    assert _file(owner, old_doc).content == b"%PDF-site"

    # 5-7. Editing B leaves A alone; A stays awarded and completed.
    assert owner.patch(f"/projects/{b}", json={"title": "Office Building Painting - 2026", "description": "Two floors, new site conditions."}).status_code == 200
    db.expire_all()
    pa = db.get(Project, a)
    assert (pa.title, pa.status.value, len(pa.drawings)) == ("Office Building Painting - 2025", "awarded", 1)
    assert db.query(Agreement).filter(Agreement.project_id == a).one().status == "completed"

    # 8-11. B is published and runs its own course: its own offers, award, completion and reviews.
    assert owner.post(f"/owner/projects/{b}/publish").status_code == 200
    assert y.get(f"/projects/{b}").status_code == 200
    _award(owner, y, b, x)
    complete_transaction(owner, y, b)
    assert y.post("/service-provider/reviews", json={"project_id": b, "rating": 3}).status_code == 200
    a_offers = {o["id"] for o in owner.get(f"/owner/projects/{a}/offers").json()}
    b_offers = {o["id"] for o in owner.get(f"/owner/projects/{b}/offers").json()}
    assert len(a_offers) == len(b_offers) == 2 and not a_offers & b_offers  # each requirement keeps its own offers
    assert {(r.project_id, r.direction) for r in db.query(Review)} == {
        (a, "owner_to_provider"), (a, "provider_to_owner"), (b, "provider_to_owner")}
    assert owner.get(f"/projects/{a}").json()["status"] == "awarded"
    assert owner.get("/owner/reputation").json()["completed_transactions"] == 2

    # 12. Again, legitimately: another new draft.
    c = owner.post(f"/owner/projects/{a}/restart", json={"creation_token": "similar-2"}).json()["id"]
    assert c not in (a, b)

    # Not from: an open requirement, a draft, a suspended one, or after leaving the organisation.
    assert owner.post(f"/owner/projects/{c}/restart").status_code == 400  # a draft
    assert owner.post(f"/owner/projects/{_tender(owner, title='Open')}/restart").status_code == 400
    pa = db.get(Project, a)
    pa.is_suspended = True
    db.commit()
    assert owner.post(f"/owner/projects/{a}/restart").status_code == 400
    pa.is_suspended = False
    db.commit()
    assert owner.delete(f"/account/organization/members/{noura_id}").status_code == 200
    assert noura.post(f"/owner/projects/{a}/restart").status_code in (403, 404)

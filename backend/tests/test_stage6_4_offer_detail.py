"""Stage 6.4: offer detail review. The owner opens one offer and sees exactly
what was submitted -- price, items, technical response, timing, assumptions,
declarations, documents -- from whom, in what state, against which version of
the requirement; under the same access rules as the inbox; read-only."""
from datetime import datetime, timedelta

from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _when
from tests.test_stage5_13_revise import REV2, _submitted, _tender

DECL = "I have visited the site."


def _local(url):
    return "/" + url.split("://", 1)[-1].split("/", 1)[-1]


def _per_item_tender(owner):
    pid = owner.post("/projects", data={"title": "Cabling", "address": "Kaifan", "description": "Lay cables.", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [
        {"description": "Cable 4x95", "quantity": "120.5", "unit": "m"}, {"description": "Terminations", "quantity": None, "unit": None}]})
    owner.put(f"/projects/{pid}/response-requirements", json={"declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def test_the_owner_reviews_exactly_what_was_submitted(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    offer = db.query(Offer).one()
    r = owner.get(f"/owner/projects/{pid}/offers/{offer.id}")
    assert r.status_code == 200, r.text
    d = r.json()
    o = d["offer"]
    # Identity, status, timing.
    assert (d["provider_name"], o["status"], o["revision"], o["project_id"]) == ("noor", "submitted", 1, pid)
    assert o["submitted_at"].endswith("Z") and d["requirement"]["id"] == pid and d["requirement"]["title"] == "HV works"
    # The response as stored.
    assert (o["amount"], o["message"], o["assumptions"], o["declarations_accepted"]) == ("1000.000", "Method v1", "A1", [DECL])
    assert (o["proposed_duration_days"], o["proposed_start_date"]) == (30, offer.proposed_start_date.isoformat())
    # What the requirement asked for, beside it.
    assert d["requirement"]["declarations"] == [DECL]
    assert d["requirement"]["requested_documents"] == [{"name": "Method statement", "required": True}]
    # The document, opened through the owner's authorised route.
    (doc,) = o["documents"]
    assert (doc["label"], doc["file_name"]) == ("Method statement", "method-v1.pdf")
    assert owner.get(_local(doc["url"])).content == b"%PDF-v1"
    # Current version, nothing outdated.
    assert d["on_current_version"] is True and o["based_on_material_revision"] == 0


def test_item_prices_are_shown_as_stored_not_recalculated(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _per_item_tender(owner)
    items = owner.get(f"/projects/{pid}").json()["items"]
    sp.post(f"/projects/{pid}/participate")
    rates = [{"item_id": items[0]["id"], "rate": "2.125"}, {"item_id": items[1]["id"], "rate": "300"}]
    assert sp.put(f"/projects/{pid}/offers/draft", json={"item_prices": rates, "accepted_declarations": [DECL]}).status_code == 200
    assert sp.post(f"/projects/{pid}/offers/draft/submit").status_code == 200, sp.get(f"/projects/{pid}/offers/draft/check").text
    offer = db.query(Offer).one()
    d = owner.get(f"/owner/projects/{pid}/offers/{offer.id}").json()
    assert d["offer"]["item_prices"] == offer.item_prices  # the stored lines, untouched
    assert d["offer"]["amount"] == f"{offer.amount:.3f}"
    assert [(i["description"], i["quantity"], i["unit"]) for i in d["requirement"]["items"]] == [("Cable 4x95", "120.500", "m"), ("Terminations", None, None)]


def test_an_amended_requirement_never_passes_an_old_offer_off_as_current(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    offer_id = db.query(Offer).one().id
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Substation plus a second bay."}, headers={"If-Match": str(v)})
    d = owner.get(f"/owner/projects/{pid}/offers/{offer_id}").json()
    assert (d["on_current_version"], d["offer"]["based_on_material_revision"], d["requirement"]["material_revision"]) == (False, 0, 1)
    # The version it answered can be read as it stood.
    assert owner.get(f"/projects/{pid}/versions/0").json()["fields"]["description"] == "Substation."
    # Revised against the amended requirement: current, and the earlier version kept with its own context.
    assert sp.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}).status_code == 200
    d = owner.get(f"/owner/projects/{pid}/offers/{offer_id}").json()
    assert (d["on_current_version"], d["offer"]["revision"], d["offer"]["amount"]) == (True, 2, "900.000")
    history = owner.get(f"/owner/projects/{pid}/offers/{offer_id}/history").json()
    assert [(h["revision_number"], h["amount"], h["based_on_material_revision"]) for h in history] == [(1, "1000.000", 0)]
    assert owner.get(_local(history[0]["documents"][0]["url"])).content == b"%PDF-v1"


def test_only_the_owner_opens_it_and_only_while_it_may_be_read(db):
    owner = _account(db, "owner", "owner@example.com")
    stranger = _account(db, "owner", "stranger@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com")
    pid, sealed, other = _tender(owner, "Visible"), _tender(owner, "Sealed", sealed=True), _tender(owner, "Other")
    _submitted(sp, pid)
    _submitted(sp, sealed)
    _submitted(rival, other)
    offer = db.query(Offer).filter(Offer.project_id == pid).one()
    sealed_offer = db.query(Offer).filter(Offer.project_id == sealed).one()
    other_offer = db.query(Offer).filter(Offer.project_id == other).one()
    url = f"/owner/projects/{pid}/offers/{offer.id}"
    assert stranger.get(url).status_code == 404
    assert sp.get(url).status_code == 403 and rival.get(url).status_code == 403
    assert owner.get(f"/owner/projects/{pid}/offers/{other_offer.id}").status_code == 404  # another requirement's offer
    assert owner.get(f"/owner/projects/{sealed}/offers/{sealed_offer.id}").status_code == 404  # sealed until the deadline
    db.get(Project, sealed).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert owner.get(f"/owner/projects/{sealed}/offers/{sealed_offer.id}").status_code == 200
    # Read-only: there is nothing to change an offer through here.
    for method in ("put", "patch", "delete"):
        assert getattr(owner, method)(url).status_code == 405
    # Withdrawn: no longer one to review.
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert owner.get(url).status_code == 404
    # The stored offer itself was never touched by any of this.
    db.expire_all()
    assert db.get(Offer, offer.id).amount == offer.amount and db.get(Offer, offer.id).message == "Method v1"

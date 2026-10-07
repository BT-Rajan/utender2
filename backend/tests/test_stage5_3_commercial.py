"""Stage 5.3: the price on the offer draft -- one total, or a rate per item on
the requirement's own items and quantities -- saved without submitting,
computed and checked by the server, private to the provider's side, and
refused from a stale page, a closed requirement or an outdated version."""
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.enums import OfferStatus
from app.models.offer import Offer
from app.models.project import Project, ProjectItem
from tests.test_stage4_9_participation import _account, _admin, _publish, _when

URL = "/projects/{}/offers/draft/commercial"
ITEMS = [
    {"description": "Supply and install 13A sockets", "quantity": "40", "unit": "nr"},
    {"description": "Cable 2.5mm", "quantity": "12.5", "unit": "m"},
    {"description": "Testing and certification"},  # no quantity: the rate is the line
]


def _itemized(owner, title="Itemized rewiring"):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Rewire a villa.", "bid_deadline": _when(10)}).json()["id"]
    assert owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": ITEMS}).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _items(db, pid):
    return sorted(db.query(ProjectItem).filter(ProjectItem.project_id == pid), key=lambda i: i.position)


def test_one_total_saved_on_the_draft_and_edited_later(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    draft = sp.post(f"/projects/{pid}/participate").json()["offer_id"]
    r = sp.put(URL.format(pid), json={"amount": "1250.500"}, headers={"If-Match": "0"})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert (saved["id"], saved["status"], Decimal(saved["amount"]), saved["item_prices"], saved["draft_version"]) == (draft, "draft", Decimal("1250.5"), None, 1)
    # Leave and return: the same price, still a draft, nothing sent to the owner.
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["id"], Decimal(mine["amount"]), mine["status"]) == (draft, Decimal("1250.5"), "draft")
    assert owner.get(f"/owner/projects/{pid}/offers").json() == [] and db.get(Project, pid).tender_type_locked is False
    # Edit, and clear: a draft may have no price yet.
    assert Decimal(sp.put(URL.format(pid), json={"amount": "1100"}, headers={"If-Match": "1"}).json()["amount"]) == Decimal("1100")
    assert sp.put(URL.format(pid), json={"amount": None}).json()["amount"] is None
    # No artificial BOQ for a requirement priced as one total.
    assert sp.put(URL.format(pid), json={"item_prices": [{"item_id": "x", "rate": "1"}]}).status_code == 400
    # Invalid values never become a price.
    for bad in ("0", "-5", "10000000000", "1.2345"):
        assert sp.put(URL.format(pid), json={"amount": bad}).status_code in (400, 422), bad
    for bad in ("abc", "NaN", "Infinity"):
        assert sp.put(URL.format(pid), json={"amount": bad}).status_code == 422, bad
    assert db.query(Offer).one().status == OfferStatus.draft


def test_quantity_times_rate_is_the_servers_total(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _itemized(owner)
    sockets, cable, testing = _items(db, pid)
    sp.post(f"/projects/{pid}/participate")
    # Partly priced: the lines so far, but no total presented as the price.
    r = sp.put(URL.format(pid), json={"item_prices": [{"item_id": sockets.id, "rate": "7.250"}]})
    assert r.status_code == 200 and r.json()["amount"] is None
    assert r.json()["item_prices"] == [{"item_id": sockets.id, "rate": "7.250", "line_total": "290.000"}]
    # Fully priced: 40 x 7.250 + 12.5 x 1.333 (= 16.6625 -> 16.663) + 150 = 456.663, whatever total the browser claims.
    rates = [{"item_id": sockets.id, "rate": "7.250"}, {"item_id": cable.id, "rate": "1.333"}, {"item_id": testing.id, "rate": "150"}]
    r = sp.put(URL.format(pid), json={"item_prices": rates, "amount": "1"})
    assert r.status_code == 200 and Decimal(r.json()["amount"]) == Decimal("456.663")
    assert [line["line_total"] for line in r.json()["item_prices"]] == ["290.000", "16.663", "150.000"]
    # Returning finds it; quantities and items are the requirement's, untouched.
    assert Decimal(sp.get(f"/projects/{pid}/offers/mine").json()["amount"]) == Decimal("456.663")
    assert [str(i.quantity) if i.quantity is not None else None for i in _items(db, pid)] == ["40.000", "12.500", None]
    # Not this requirement's item, the same item twice, a negative or over-precise rate: refused.
    assert sp.put(URL.format(pid), json={"item_prices": [{"item_id": "not-an-item", "rate": "1"}]}).status_code == 400
    assert sp.put(URL.format(pid), json={"item_prices": [{"item_id": sockets.id, "rate": "1"}, {"item_id": sockets.id, "rate": "2"}]}).status_code == 400
    assert sp.put(URL.format(pid), json={"item_prices": [{"item_id": sockets.id, "rate": "-1"}]}).status_code == 422
    assert sp.put(URL.format(pid), json={"item_prices": [{"item_id": sockets.id, "rate": "1.0001"}]}).status_code == 422
    assert sp.put(URL.format(pid), json={"item_prices": [{"item_id": sockets.id, "rate": "999999999999"}]}).status_code == 400
    # All zero: not a price.
    zero = [{"item_id": i.id, "rate": "0"} for i in (sockets, cable, testing)]
    assert sp.put(URL.format(pid), json={"item_prices": zero}).json()["amount"] is None
    # Submitting later still works through the existing route, on the same row.
    offer = sp.post(f"/projects/{pid}/offers", json={"item_prices": rates}).json()
    assert offer["status"] == "submitted" and Decimal(offer["amount"]) == Decimal("456.663") and db.query(Offer).count() == 1
    # Once submitted, the draft route no longer changes it.
    assert sp.put(URL.format(pid), json={"item_prices": rates}).status_code == 409


def test_stale_pages_and_other_sides_are_refused(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    rival = _account(db, "service_provider", "rival@example.com")
    pid = _publish(owner)
    boss.post(f"/projects/{pid}/participate")
    # Two members (or two tabs) open version 0; the first save wins, the second is refused, not overwritten.
    assert boss.put(URL.format(pid), json={"amount": "900"}, headers={"If-Match": "0"}).status_code == 200
    r = eng.put(URL.format(pid), json={"amount": "800"}, headers={"If-Match": "0"})
    assert r.status_code == 409 and "changed somewhere else" in r.json()["detail"]
    assert Decimal(eng.get(f"/projects/{pid}/offers/mine").json()["amount"]) == Decimal("900")  # the same organization draft
    r = eng.put(URL.format(pid), json={"amount": "800"}, headers={"If-Match": "1"})
    assert r.status_code == 200 and db.query(Offer).one().updated_by == eng.get("/auth/me").json()["id"]
    # Another provider: no draft of theirs to save into, and none of the organization's reachable.
    r = rival.put(URL.format(pid), json={"amount": "1", "offer_id": db.query(Offer).one().id, "service_provider_id": boss.get("/auth/me").json()["id"]})
    assert r.status_code == 404
    db.expire_all()
    assert Decimal(db.query(Offer).one().amount) == Decimal("800") and db.query(Offer).count() == 1
    # The requirement itself can't be changed from here.
    assert rival.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": ITEMS}).status_code in (403, 404)


def test_the_requirement_decides_when_the_price_can_change(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    amended, paused, suspended, expiring, canceled = (_publish(owner, t) for t in ("Amended", "Paused", "Suspended", "Expiring", "Canceled"))
    for pid in (amended, paused, suspended, expiring, canceled):
        sp.post(f"/projects/{pid}/participate")
        assert sp.put(URL.format(pid), json={"amount": "500"}).status_code == 200
    # A material change while editing: refused until the current requirement has been reviewed.
    v = owner.get(f"/projects/{amended}").json()["version"]
    owner.patch(f"/projects/{amended}", json={"description": "Rewire a villa: 40 points plus 6 outdoor."}, headers={"If-Match": str(v)})
    r = sp.put(URL.format(amended), json={"amount": "550"})
    assert r.status_code == 409 and "Review the current requirement" in r.json()["detail"]
    sp.post(f"/projects/{amended}/participate")  # reviewed
    assert Decimal(sp.put(URL.format(amended), json={"amount": "550"}).json()["amount"]) == Decimal("550")
    # Paused, suspended, past its deadline, ended: the draft keeps its price but can't change.
    owner.post(f"/owner/projects/{paused}/pause", json={"reason": "Waiting for the permit."})
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})
    db.get(Project, expiring).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.post(f"/owner/projects/{canceled}/cancel", json={"reason": "not_needed"})
    for pid in (paused, suspended, expiring, canceled):
        assert sp.put(URL.format(pid), json={"amount": "1"}).status_code == 400, pid
    db.expire_all()
    assert {o.amount for o in db.query(Offer).filter(Offer.project_id != amended)} == {Decimal("500")}
    assert all(o.status == OfferStatus.draft for o in db.query(Offer))
    # Arabic.
    r = sp.put(URL.format(paused), json={"amount": "1"}, headers={"Accept-Language": "ar"})
    assert r.status_code == 400 and r.json()["detail"] != "Bidding on this project is closed."

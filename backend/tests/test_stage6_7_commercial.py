"""Stage 6.7: commercial evaluation. The owner sees each offer's actual
commercial terms -- total, currency, item rates, quantities, units, line
totals, assumptions/exclusions -- exactly as the server computed and stored
them, the same in the inbox, the offer page and the comparison; never ranked
by price; never to another provider."""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.models.offer import Offer
from tests.test_stage4_9_participation import _account, _when
from tests.test_stage5_13_revise import _submitted, _tender

DECL = "I have visited the site."


def _itemized(owner):
    pid = owner.post("/projects", data={"title": "Cabling", "address": "Kaifan", "description": "Lay cables.", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [
        {"description": "Cable 4x95", "quantity": "120.5", "unit": "m"}, {"description": "Terminations", "quantity": None, "unit": None}]})
    owner.put(f"/projects/{pid}/response-requirements", json={"declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _price(sp, pid, rates, **extra):
    items = sp.get(f"/projects/{pid}").json()["items"]
    sp.post(f"/projects/{pid}/participate")
    lines = [{"item_id": i["id"], "rate": r, **extra} for i, r in zip(items, rates)]
    # A browser-sent total (and line totals) are ignored: the server prices it.
    r = sp.put(f"/projects/{pid}/offers/draft", json={"amount": "1.000", "item_prices": lines, "accepted_declarations": [DECL], "assumptions": f"Excludes civil works ({rates[0]})"})
    assert r.status_code == 200, r.text
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code == 200, r.text
    return r.json()


def _expected(items, rates):
    lines = []
    for item, rate in zip(items, rates):
        q = Decimal(item["quantity"]) if item["quantity"] is not None else None
        lines.append((Decimal(rate) * q if q is not None else Decimal(rate)).quantize(Decimal("0.001"), ROUND_HALF_UP))
    return lines, sum(lines)


def test_itemized_offers_are_priced_by_the_server_and_shown_as_stored(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _itemized(owner)
    items = owner.get(f"/projects/{pid}").json()["items"]
    _price(a, pid, ["2.125", "300"], line_total="999999")
    _price(b, pid, ["1.990", "450.5"])
    inbox = {o["service_provider_company_name"]: o for o in owner.get(f"/owner/projects/{pid}/offers").json()}
    for name, rates in (("amal", ["2.125", "300"]), ("badr", ["1.990", "450.5"])):
        lines, total = _expected(items, rates)
        o = inbox[name]
        # Internally consistent: each line = rate x quantity (3 decimals), total = their sum.
        assert [Decimal(l["line_total"]) for l in o["item_prices"]] == lines, name
        assert [Decimal(l["rate"]) for l in o["item_prices"]] == [Decimal(r) for r in rates]
        assert Decimal(o["amount"]) == total != Decimal("1.000")
        # The offer page and the comparison show the same stored figures, with the requirement's quantities and units.
        detail = owner.get(f"/owner/projects/{pid}/offers/{o['id']}").json()
        assert (detail["offer"]["amount"], detail["offer"]["item_prices"]) == (o["amount"], o["item_prices"])
        assert [(i["quantity"], i["unit"]) for i in detail["requirement"]["items"]] == [("120.500", "m"), (None, None)]
        assert detail["requirement"]["pricing_basis"] == "per_item" and detail["requirement"]["currency"]
        assert detail["offer"]["assumptions"] == f"Excludes civil works ({rates[0]})"
    compared = owner.get(f"/owner/projects/{pid}/offers/compare", params=[("ids", inbox["amal"]["id"]), ("ids", inbox["badr"]["id"])]).json()["offers"]
    assert [(o["amount"], o["item_prices"]) for o in compared] == [(inbox[n]["amount"], inbox[n]["item_prices"]) for n in ("amal", "badr")]
    # Stored exactly as listed.
    listed = {o["id"]: o for o in inbox.values()}
    for o in db.query(Offer).filter(Offer.project_id == pid):
        assert (f"{o.amount:.3f}", o.item_prices) == (listed[o.id]["amount"], listed[o.id]["item_prices"])


def test_a_total_price_service_and_a_list_never_ranked_by_price(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana"))
    pid = _tender(owner)  # one total price
    for sp, amount in ((a, "1500"), (b, "1000"), (c, "1200")):
        _submitted(sp, pid)
        if amount != "1000":
            r = sp.post(f"/projects/{pid}/offers", json={"amount": amount, "message": "Method v1", "assumptions": "A1", "accepted_declarations": [DECL], "proposed_duration_days": 30}, headers={"If-Match": "1"})
            assert r.status_code == 200, r.text
    # Arrivals a second apart (MySQL keeps whole seconds; within one second the order is by id).
    me = {sp.get("/auth/me").json()["id"]: n for n, sp in enumerate((a, b, c))}
    for o in db.query(Offer).filter(Offer.project_id == pid):
        o.submitted_at = datetime(2026, 1, 1, 9, 0, me[o.service_provider_id])
    db.commit()
    listed = owner.get(f"/owner/projects/{pid}/offers").json()
    # In the order they came in -- not cheapest first.
    assert [o["service_provider_company_name"] for o in listed] == ["amal", "badr", "dana"]
    assert [o["amount"] for o in listed] == ["1500.000", "1000.000", "1200.000"]
    assert all(o["item_prices"] is None for o in listed)
    # Nothing labels a cheapest or best offer.
    assert not any(k in str(listed).lower() for k in ("cheapest", "best", "rank", "score", "recommend"))


def test_withdrawn_revised_amended_and_competitors(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    # Revised: the current price is the revision; the earlier one stays in the history.
    r = a.post(f"/projects/{pid}/offers", json={"amount": "850.500", "message": "Method v2", "accepted_declarations": [DECL], "proposed_duration_days": 30}, headers={"If-Match": "1"})
    assert r.status_code == 200, r.text
    a_id = r.json()["id"]
    assert owner.get(f"/owner/projects/{pid}/offers/{a_id}").json()["offer"]["amount"] == "850.500"
    assert [h["amount"] for h in owner.get(f"/owner/projects/{pid}/offers/{a_id}/history").json()] == ["1000.000"]
    # Malformed prices are refused, never stored or rounded.
    for bad in ("-5", "10.0005", "abc"):
        assert a.post(f"/projects/{pid}/offers", json={"amount": bad, "message": "x", "accepted_declarations": [DECL]}, headers={"If-Match": "2"}).status_code in (400, 422), bad
    assert owner.get(f"/owner/projects/{pid}/offers/{a_id}").json()["offer"]["amount"] == "850.500"
    # Amended after submission: B's price stays as it was, against the version it answered.
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Substation plus a second bay."}, headers={"If-Match": str(v)})
    b_row = next(o for o in owner.get(f"/owner/projects/{pid}/offers").json() if o["service_provider_company_name"] == "badr")
    assert (b_row["amount"], b_row["based_on_material_revision"]) == ("1000.000", 0)
    # Withdrawn: no longer a commercial proposal -- its price isn't shown to the owner.
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    b_row = next(o for o in owner.get(f"/owner/projects/{pid}/offers").json() if o["service_provider_company_name"] == "badr")
    assert b_row["status"] == "withdrawn" and b_row["amount"] is None
    # A competitor never gets another provider's price, by any owner route.
    for url in (f"/owner/projects/{pid}/offers", f"/owner/projects/{pid}/offers/{a_id}", f"/owner/projects/{pid}/offers/compare?ids={a_id}"):
        r = b.get(url)
        assert r.status_code == 403 and "850" not in r.text, url
    assert "850.500" not in b.get(f"/projects/{pid}/offers/mine").text and "850.500" not in b.get(f"/projects/{pid}").text

"""Stage 5.9: the offer preview -- the provider's stored offer exactly as
submission would send it, read fresh each time (no preview copy), beside the
requirement as it is now and the quality gate's verdict; only for the
provider's own side; and never submitting, sealing or locking anything."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.enums import OfferStatus
from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _publish, _when

PREVIEW = "/projects/{}/offers/draft/preview"
D = "/projects/{}/offers/draft/"
DECL = "I have visited the site."
RULES = {"approach": "required", "documents": [{"name": "Method statement", "required": True}, {"name": "Catalogue", "required": False}], "declarations": [DECL]}


def _d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _itemized(owner):
    pid = owner.post("/projects", data={"title": "Substation BOQ", "address": "Kaifan", "description": "Replace the transformer.\nTest and commission.", "bid_deadline": _when(10), "expected_start_date": _d(20), "expected_duration_days": "30"}).json()["id"]
    owner.patch(f"/projects/{pid}", json={"governorate": "hawalli", "area": "Salmiya"})
    owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [{"description": "Transformer", "quantity": "2", "unit": "nr"}, {"description": "Testing"}]})
    owner.put(f"/projects/{pid}/response-requirements", json=RULES)
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def test_preview_is_the_stored_offer_and_follows_every_save(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _itemized(owner)
    offer_id = sp.post(f"/projects/{pid}/participate").json()["offer_id"]
    a, b = sorted(db.get(Project, pid).items, key=lambda i: i.position)
    # Incomplete: previewable, every missing part named, never "ready".
    p = sp.get(PREVIEW.format(pid)).json()
    assert p["offer"]["id"] == offer_id and p["offer"]["status"] == "draft" and p["readiness"]["ready"] is False
    assert {i["section"] for i in p["readiness"]["issues"]} == {"price", "technical", "documents", "declarations"}
    # Complete the offer.
    sp.put(D.format(pid) + "commercial", json={"item_prices": [{"item_id": a.id, "rate": "4000"}, {"item_id": b.id, "rate": "750.5"}]})
    sp.put(D.format(pid) + "technical", json={"message": "Isolate, swap, test."})
    sp.put(D.format(pid) + "timing", json={"proposed_start_date": _d(22), "proposed_duration_days": 30})
    sp.put(D.format(pid) + "assumptions", json={"assumptions": "Excludes civil works."})
    sp.put(D.format(pid) + "declarations", json={"accepted_declarations": [DECL]})
    sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("method.pdf", b"%PDF", "application/pdf")})
    p = sp.get(PREVIEW.format(pid)).json()
    req, offer = p["requirement"], p["offer"]
    # Requirement identity and context, as it is now.
    assert (req["title"], req["governorate"], req["area"], req["pricing_basis"], req["currency"], req["material_revision"], req["amendment_number"]) == (
        "Substation BOQ", "hawalli", "Salmiya", "per_item", "KWD", 0, None)
    assert [i["description"] for i in req["items"]] == ["Transformer", "Testing"] and req["expected_duration_days"] == 30
    assert req["declarations"] == [DECL] and req["requested_documents"] == [{"name": "Method statement", "required": True}, {"name": "Catalogue", "required": False}]
    assert p["provider_name"] == "noor" and p["on_current_version"] is True
    # Every part of the offer, exactly as stored.
    assert Decimal(offer["amount"]) == Decimal("8750.500") and [l["line_total"] for l in offer["item_prices"]] == ["8000.000", "750.500"]
    assert (offer["message"], offer["proposed_start_date"], offer["proposed_duration_days"], offer["assumptions"], offer["declarations_accepted"]) == (
        "Isolate, swap, test.", _d(22), 30, "Excludes civil works.", [DECL])
    assert [(d["label"], d["file_name"]) for d in offer["documents"]] == [("Method statement", "method.pdf")]
    assert "/offer-documents/" in offer["documents"][0]["url"] and "file_path" not in offer["documents"][0]
    assert p["readiness"] == {"ready": True, "issues": []}
    # Back to edit, change, preview again: the latest saved values, nothing stale.
    sp.put(D.format(pid) + "commercial", json={"item_prices": [{"item_id": a.id, "rate": "3900"}, {"item_id": b.id, "rate": "750.5"}]})
    sp.put(D.format(pid) + "assumptions", json={"assumptions": "Excludes civil works and cabling."})
    sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("method-v2.pdf", b"%PDF2", "application/pdf")})
    again = sp.get(PREVIEW.format(pid)).json()["offer"]
    assert Decimal(again["amount"]) == Decimal("8550.500") and again["assumptions"] == "Excludes civil works and cabling."
    assert [d["file_name"] for d in again["documents"]] == ["method-v2.pdf"]
    # Previewing submitted, sealed and locked nothing.
    offer_row = db.query(Offer).one()
    db.refresh(offer_row)
    assert offer_row.status == OfferStatus.draft and db.get(Project, pid).tender_type_locked is False
    assert owner.get(f"/owner/projects/{pid}/offers").json() == [] and sp.get("/service-provider/my-bids").json() == []


def test_amended_requirement_previews_against_the_current_version(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    sp.post(f"/projects/{pid}/participate")
    sp.put(D.format(pid) + "commercial", json={"amount": "900"})
    assert sp.get(PREVIEW.format(pid)).json()["readiness"]["ready"] is True
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Rewire a villa: 40 points plus 6 outdoor."}, headers={"If-Match": str(v)})
    p = sp.get(PREVIEW.format(pid)).json()
    # The current requirement, flagged as changed since the offer was started; not ready.
    assert p["requirement"]["description"].endswith("6 outdoor.") and p["requirement"]["material_revision"] == 1 and p["requirement"]["amendment_number"] == 1
    assert p["on_current_version"] is False and p["readiness"]["ready"] is False
    assert [i["section"] for i in p["readiness"]["issues"]] == ["requirement"]
    sp.post(f"/projects/{pid}/participate")  # reviewed
    p = sp.get(PREVIEW.format(pid)).json()
    assert p["on_current_version"] is True and p["readiness"]["ready"] is True


def test_only_the_providers_own_offer(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    rival = _account(db, "service_provider", "rival@example.com")
    pid, other = _publish(owner, "Villa"), _publish(owner, "Warehouse")
    boss.post(f"/projects/{pid}/participate")
    boss.put(D.format(pid) + "commercial", json={"amount": "1234"})
    # The organization's members share it.
    assert Decimal(eng.get(PREVIEW.format(pid)).json()["offer"]["amount"]) == Decimal("1234")
    # Another provider -- whatever ids are added -- has nothing to preview; nor does anyone on another requirement.
    offer = db.query(Offer).one()
    r = rival.get(PREVIEW.format(pid), params={"offer_id": offer.id, "service_provider_id": offer.service_provider_id, "organization_id": offer.organization_id})
    assert r.status_code == 404 and "1234" not in r.text
    assert boss.get(PREVIEW.format(other)).status_code == 404
    assert owner.get(PREVIEW.format(pid)).status_code == 403  # not a provider
    draft = owner.post("/projects", data={"title": "Draft", "address": "x", "bid_deadline": _when(9)}).json()["id"]
    assert boss.get(PREVIEW.format(draft)).status_code == 404

"""Stage 6.8: technical evaluation. The owner reviews each provider's
technical response -- word for word -- beside what the requirement asked:
its scope, items with their specifications (whatever the pricing basis),
whether a technical response and completion period were required, the
documents it asked for, and the version the offer answered."""
from app.models.offer import Offer
from tests.test_stage4_9_participation import _account, _when

DECL = "I have visited the site."
METHOD = "  Phase 1: isolate the feeder.\n\nPhase 2: replace the 11 kV switchgear (IEC 62271-200).\nالمرحلة ٣: الاختبار والتشغيل  "


def _tender(owner, pricing="lump_sum"):
    pid = owner.post("/projects", data={"title": "Switchgear", "address": "Kaifan", "description": "Replace the 11 kV switchgear.", "bid_deadline": _when(10)}).json()["id"]
    items = [{"description": "11 kV panel", "quantity": "4", "unit": "nr", "specification": "IEC 62271-200, 630 A, IP4X"},
             {"description": "Commissioning", "quantity": None, "unit": None, "specification": None}]
    assert owner.put(f"/projects/{pid}/items", json={"pricing_basis": pricing, "items": items}).status_code == 200
    owner.put(f"/projects/{pid}/response-requirements", json={
        "approach": "required", "completion_period": "required",
        "documents": [{"name": "Method statement", "required": True}, {"name": "Product catalogue", "required": False}], "declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _submit(sp, pid, method=METHOD, period="12 weeks"):
    sp.post(f"/projects/{pid}/participate")
    assert sp.put(f"/projects/{pid}/offers/draft", json={"amount": "5000", "message": method, "timeline_estimate": period, "accepted_declarations": [DECL]}).status_code == 200
    sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("method.pdf", b"%PDF-method", "application/pdf")})
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _local(url):
    return "/" + url.split("://", 1)[-1].split("/", 1)[-1]


def test_the_technical_response_word_for_word_beside_what_was_asked(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    offer_id = _submit(sp, pid)
    d = owner.get(f"/owner/projects/{pid}/offers/{offer_id}").json()
    req, o = d["requirement"], d["offer"]
    # Exactly as stored (saving trims only the outer whitespace, Stage 5.4): line breaks, wording, Arabic -- untouched.
    assert o["message"] == db.get(Offer, offer_id).message == METHOD.strip()
    assert o["timeline_estimate"] == "12 weeks"
    # What the requirement asked for: technical response and completion period required, the documents, the scope and items with specifications.
    assert (req["approach"], req["completion_period"]) == ("required", "required")
    assert req["requested_documents"] == [{"name": "Method statement", "required": True}, {"name": "Product catalogue", "required": False}]
    assert req["description"] == "Replace the 11 kV switchgear." and req["pricing_basis"] == "lump_sum"
    assert [(i["description"], i["quantity"], i["unit"], i["specification"]) for i in req["items"]] == [
        ("11 kV panel", "4.000", "nr", "IEC 62271-200, 630 A, IP4X"), ("Commissioning", None, None, None)]
    # The technical document attached, opened through the owner's route; the optional one simply isn't there (not filled in).
    assert [(x["label"], x["file_name"]) for x in o["documents"]] == [("Method statement", "method.pdf")]
    assert owner.get(_local(o["documents"][0]["url"])).content == b"%PDF-method"
    # The version answered, readable as it stood.
    assert o["based_on_material_revision"] == 0 and owner.get(f"/projects/{pid}/versions/0").json()["fields"]["description"] == "Replace the 11 kV switchgear."


def test_optional_parts_are_not_forced_and_missing_required_ones_never_reach_the_owner(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    sp.post(f"/projects/{pid}/participate")
    sp.put(f"/projects/{pid}/offers/draft", json={"amount": "5000", "message": "", "timeline_estimate": "", "accepted_declarations": [DECL]})
    assert sp.post(f"/projects/{pid}/offers/draft/submit").status_code in (400, 422)
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    # Per-item requirements carry the same specifications.
    per_item = _tender(owner, pricing="per_item")
    req = owner.get(f"/projects/{per_item}").json()
    assert [i["specification"] for i in req["items"]] == ["IEC 62271-200, 630 A, IP4X", None]


def test_revised_withdrawn_amended_and_competitors(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    a_id, b_id = _submit(a, pid), _submit(b, pid, method="Badr's method: modular panels.")
    # Amended after A and B submitted: their responses keep version 0.
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Replace the 11 kV switchgear and the RMU."}, headers={"If-Match": str(v)})
    d = owner.get(f"/owner/projects/{pid}/offers/{a_id}").json()
    assert (d["on_current_version"], d["offer"]["message"]) == (False, METHOD.strip())
    # A revises against the amended requirement: the current response is the revision; the earlier one is history.
    r = a.post(f"/projects/{pid}/offers", json={"amount": "5200", "message": "Method v2 incl. RMU.", "timeline_estimate": "14 weeks", "accepted_declarations": [DECL]}, headers={"If-Match": "1"})
    assert r.status_code == 200, r.text
    d = owner.get(f"/owner/projects/{pid}/offers/{a_id}").json()
    assert (d["on_current_version"], d["offer"]["message"], d["offer"]["timeline_estimate"]) == (True, "Method v2 incl. RMU.", "14 weeks")
    assert [(h["message"], h["based_on_material_revision"]) for h in owner.get(f"/owner/projects/{pid}/offers/{a_id}/history").json()] == [(METHOD.strip(), 0)]
    # A competitor never reaches A's technical response or documents.
    for url in (f"/owner/projects/{pid}/offers/{a_id}", f"/owner/projects/{pid}/offers/{a_id}/history",
                f"/owner/projects/{pid}/offers/{a_id}/documents/file?label=Method%20statement"):
        r = b.get(url, follow_redirects=False)
        assert r.status_code == 403 and "RMU" not in r.text and "%PDF" not in r.text, url
    assert "RMU" not in b.get(f"/projects/{pid}/offers/mine").text
    # Withdrawn: no longer a technical response to review.
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert owner.get(f"/owner/projects/{pid}/offers/{b_id}").status_code == 404
    row = next(o for o in owner.get(f"/owner/projects/{pid}/offers").json() if o["id"] == b_id)
    assert row["message"] is None and row["documents"] == []

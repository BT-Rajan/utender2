"""Stage 4.4: a provider who opens an opportunity reads the whole published
requirement -- the same record the owner previewed -- with its current
deadline, amendments, documents, rules and whether they may respond; and
nothing they aren't entitled to."""
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.document import DocumentRequirement, ServiceProviderDocument
from app.models.enums import DocumentStatus, UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile

SCOPE = "Supply and install a 3-phase DB board and 40 lighting points across two floors of a villa in Kaifan.\nTesting and commissioning included."


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _verified(db, role: str, email: str, paid: bool = True) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.company_name = email.split("@")[0]
        profile.payment_override_active = paid
    db.commit()
    return c


def _fetch(client, url):
    return client.get("/" + url.split("://", 1)[-1].split("/", 1)[-1])


def _full_requirement(db, owner):
    licence = DocumentRequirement(name="Electrical works licence", is_required=False, applies_to=UserRole.service_provider)
    db.add(licence)
    db.commit()
    start = (date.today() + timedelta(days=40)).isoformat()
    pid = owner.post(
        "/projects",
        data={"title": "Villa rewiring", "address": "Kaifan, block 4, street 41, house 12", "governorate": "capital", "area": "Kaifan", "trade": "Electrical", "description": SCOPE, "bid_deadline": _when(12), "expected_start_date": start, "expected_duration_days": "20"},
        files=[("drawings", ("single-line.pdf", b"%PDF-sld", "application/pdf"))],
    ).json()["id"]
    owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [{"description": "DB board", "quantity": "1", "unit": "no.", "specification": "3-phase, 24 ways"}, {"description": "Lighting point", "quantity": "40", "unit": "no."}]})
    owner.put(f"/projects/{pid}/response-requirements", json={"completion_period": "required", "approach": "optional", "documents": [{"name": "Method statement", "required": True}], "declarations": ["I have visited the site."]})
    owner.put(f"/projects/{pid}/tender-rules", json={"commercial_conditions": {"offer_validity_days": 60, "warranty_months": 12}, "bidder_instructions": "Site visits Sat–Thu, 8–12."})
    owner.put(f"/projects/{pid}/eligibility", json={"qualifications": [licence.id]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid, licence, start


def _hold(db, client, licence, expires=None):
    uid = client.get("/auth/me").json()["id"]
    doc = db.query(ServiceProviderDocument).filter_by(service_provider_id=uid, requirement_id=licence.id).first() or ServiceProviderDocument(service_provider_id=uid, requirement_id=licence.id)
    doc.status, doc.expires_on = DocumentStatus.approved, expires
    db.add(doc)
    db.commit()
    return doc


def test_the_provider_reads_the_whole_published_requirement(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "noor@example.com")
    pid, licence, start = _full_requirement(db, owner)
    _hold(db, sp, licence)
    # Extended, then materially amended after publication.
    v = owner.get(f"/projects/{pid}").json()["version"]
    later = _when(20)
    owner.patch(f"/projects/{pid}", json={"bid_deadline": later, "description": SCOPE + "\nInclude 4 outdoor points."}, headers={"If-Match": str(v)})

    assert any(p["id"] == pid for p in sp.get("/service-provider/feed").json()["items"])  # 1. from the feed
    r = sp.get(f"/projects/{pid}").json()
    # 2-3. What, where, scope, quantities/specifications, timing, pricing basis.
    assert (r["title"], r["trade"], r["governorate"], r["area"], r["address"]) == ("Villa rewiring", "Electrical", "capital", "Kaifan", "Kaifan, block 4, street 41, house 12")
    assert r["description"].endswith("Include 4 outdoor points.") and r["pricing_basis"] == "per_item"
    assert [(i["description"], i["quantity"], i["specification"]) for i in r["items"]] == [("DB board", "1.000", "3-phase, 24 ways"), ("Lighting point", "40.000", None)]
    assert (r["expected_start_date"], r["expected_duration_days"]) == (start, 20)
    # 4. Documents, through the secure file links.
    assert _fetch(sp, r["drawings"][0]["url"]).content == b"%PDF-sld"
    # 5. What to submit, and the commercial rules.
    assert r["response_requirements"]["completion_period"] == "required" and r["response_requirements"]["documents"][0]["name"] == "Method statement"
    assert r["tender_rules"]["commercial_conditions"]["offer_validity_days"] == 60 and r["tender_rules"]["bidder_instructions"].startswith("Site visits")
    # 6. The current deadline; 8. the state; 9. the amendment.
    assert r["bid_deadline"] == later and r["status"] == "open" and r["material_revision"] == 1
    assert any(a["material"] for a in sp.get(f"/projects/{pid}/amendments").json())
    # 7. Eligibility: theirs, with the rules.
    assert r["eligible"] is True and r["ineligible_reasons"] == [] and r["provider_eligibility"]["qualifications"][0]["name"] == "Electrical works licence"
    # The same record the owner previews -- not a provider copy.
    mine = owner.get(f"/projects/{pid}").json()
    for field in ("title", "description", "items", "bid_deadline", "provider_eligibility", "response_requirements", "tender_rules", "pricing_basis"):
        assert r[field] == mine[field], field
    # Owner-only details stay with the owner.
    assert r["closure_note"] is None and r["restarted_from_id"] is None


def test_a_lapsed_qualification_is_explained_and_still_enforced(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "noor@example.com")
    licence = DocumentRequirement(name="Electrical works licence", is_required=False, applies_to=UserRole.service_provider)
    db.add(licence)
    db.commit()
    pid = owner.post("/projects", data={"title": "Rewiring", "address": "Salwa", "description": "Rewire a flat.", "bid_deadline": _when(9)}).json()["id"]
    owner.put(f"/projects/{pid}/eligibility", json={"qualifications": [licence.id]})
    owner.post(f"/owner/projects/{pid}/publish")
    doc = _hold(db, sp, licence)
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 200
    doc.expires_on = date.today() - timedelta(days=1)
    db.commit()
    # The bidder keeps sight of it, told exactly why they can no longer revise...
    r = sp.get(f"/projects/{pid}").json()
    assert r["eligible"] is False and [x["code"] for x in r["ineligible_reasons"]] == ["qualification_expired"]
    # ...and the server holds to it.
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "800"}).status_code == 403


def test_nothing_reaches_who_isnt_entitled(db):
    owner = _verified(db, "owner", "owner@example.com")
    other_owner = _verified(db, "owner", "other@example.com")
    unpaid = _verified(db, "service_provider", "free@example.com", paid=False)
    unqualified = _verified(db, "service_provider", "sami@example.com")
    pid, licence, _ = _full_requirement(db, owner)
    url = owner.get(f"/projects/{pid}").json()["drawings"][0]["url"]
    for client in (other_owner, unpaid, unqualified):
        assert client.get(f"/projects/{pid}").status_code == 404
        assert client.get(f"/projects/{pid}/drawings-zip").status_code == 404
    assert TestClient(app).get(f"/projects/{pid}").status_code in (401, 403)
    # The unqualified provider is told why, without the requirement itself.
    reasons = unqualified.get(f"/projects/{pid}/eligibility").json()
    assert reasons["eligible"] is False and reasons["reasons"][0]["code"] == "qualification_missing"
    # A signed link for one requirement's file doesn't open another file.
    tampered = url.replace("single-line.pdf", "other.pdf")
    assert _fetch(unqualified, tampered).status_code in (403, 404)
    # A draft can't be reached by guessing its id.
    draft = owner.post("/projects", data={"title": "Secret", "address": "x", "bid_deadline": _when(9)}).json()["id"]
    assert unqualified.get(f"/projects/{draft}").status_code == 404 and unqualified.get(f"/projects/{draft}/amendments").status_code == 404
    # Ended: only providers who took part still see it.
    open_pid = owner.post("/projects", data={"title": "Open to all", "address": "y", "description": "Paint a fence.", "bid_deadline": _when(9), "status": "open"}).json()["id"]
    assert unqualified.get(f"/projects/{open_pid}").status_code == 200
    owner.post(f"/owner/projects/{open_pid}/cancel", json={"reason": "not_needed"})
    assert unqualified.get(f"/projects/{open_pid}").status_code == 404


def test_documents_say_how_large_they_are(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sami@example.com")
    pid = owner.post("/projects", data={"title": "Fence", "address": "x", "description": "Paint a fence.", "bid_deadline": _when(9), "status": "open"}, files=[("drawings", ("plan.pdf", b"%PDF" + b"0" * 2044, "application/pdf"))]).json()["id"]
    assert sp.get(f"/projects/{pid}").json()["drawings"][0]["size_bytes"] == 2048
    owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("plan.pdf", b"%PDF-2", "application/pdf"))])  # a replacement, measured too
    assert [(d["revision"], d["size_bytes"]) for d in sp.get(f"/projects/{pid}/drawings/history").json()] == [(1, 2048), (2, 6)]


def test_who_cant_open_it_still_learns_what_it_is_and_why(db):
    owner = _verified(db, "owner", "owner@example.com")
    unqualified = _verified(db, "service_provider", "sami@example.com")
    unpaid = _verified(db, "service_provider", "free@example.com", paid=False)
    pid, licence, _ = _full_requirement(db, owner)
    _hold(db, unpaid, licence)

    # Not qualified: the listing (never the address or scope) and the reasons.
    r = unqualified.get(f"/projects/{pid}/eligibility").json()
    assert r["eligible"] is False and r["listing"]["title"] == "Villa rewiring" and r["listing"]["governorate"] == "capital"
    assert "address" not in r["listing"] and "description" not in r["listing"] and "Kaifan, block 4" not in str(r)
    # Qualified but without full access yet: the listing, so the page can say how to open it.
    r = unpaid.get(f"/projects/{pid}/eligibility").json()
    assert r["eligible"] is True and r["listing"]["title"] == "Villa rewiring"
    assert unpaid.get(f"/projects/{pid}").status_code == 404  # the requirement itself still needs access
    # Once it has ended, no listing for those who didn't take part.
    owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "not_needed"})
    assert unqualified.get(f"/projects/{pid}/eligibility").json()["listing"] is None

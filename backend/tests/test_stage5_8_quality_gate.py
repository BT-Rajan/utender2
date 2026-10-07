"""Stage 5.8: the offer quality gate -- is this provider's saved offer complete
and valid enough to submit, against the requirement as it is now? Only what
this requirement asks for (Stage 3.8), every issue listed by part of the
offer, judged by the server; and submission makes its own checks again, so
neither a stale "ready" nor a direct API call gets round it."""
from datetime import date, datetime, timedelta

from app.models.enums import OfferStatus
from app.models.offer import Offer
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from tests.test_stage4_9_participation import _account, _admin, _publish, _when

CHECK = "/projects/{}/offers/draft/check"
D = "/projects/{}/offers/draft/"
DECL = "I have visited the site."
RULES = {"approach": "required", "completion_period": "required", "documents": [{"name": "Method statement", "required": True}, {"name": "Catalogue", "required": False}], "declarations": [DECL]}


def _d(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _demanding(owner, title="Substation works", rules=RULES, eligibility=None):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "HV works.", "bid_deadline": _when(10)}).json()["id"]
    owner.patch(f"/projects/{pid}", json={"governorate": "hawalli"})
    assert owner.put(f"/projects/{pid}/response-requirements", json=rules).status_code == 200
    if eligibility:
        assert owner.put(f"/projects/{pid}/eligibility", json=eligibility).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _complete(sp, pid):
    assert sp.put(D.format(pid) + "commercial", json={"amount": "12500"}).status_code == 200
    assert sp.put(D.format(pid) + "technical", json={"message": "Isolate, replace, test, commission."}).status_code == 200
    assert sp.put(D.format(pid) + "timing", json={"proposed_start_date": _d(20), "proposed_duration_days": 30}).status_code == 200
    assert sp.put(D.format(pid) + "declarations", json={"accepted_declarations": [DECL]}).status_code == 200
    assert sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("m.pdf", b"%PDF", "application/pdf")}).status_code == 200


def _sections(sp, pid):
    r = sp.get(CHECK.format(pid))
    assert r.status_code == 200, r.text
    return r.json()["ready"], sorted({i["section"] for i in r.json()["issues"]}), r.json()["issues"]


def test_complete_ready_and_each_missing_part_named(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _demanding(owner)
    sp.post(f"/projects/{pid}/participate")
    # 7. An empty draft saves fine -- and the gate lists everything still to do, by part.
    ready, sections, issues = _sections(sp, pid)
    assert not ready and sections == ["declarations", "documents", "price", "technical", "timing"]
    assert any('"Method statement"' in i["message"] for i in issues) and not any("Catalogue" in i["message"] for i in issues)
    # 1. Complete -> ready; 6. the optional document (Catalogue) and assumptions aren't needed.
    _complete(sp, pid)
    assert _sections(sp, pid)[:2] == (True, [])
    # 2. Price removed -> not ready (price).
    sp.put(D.format(pid) + "commercial", json={"amount": None})
    assert _sections(sp, pid)[:2] == (False, ["price"])
    sp.put(D.format(pid) + "commercial", json={"amount": "12500"})
    # 3. Technical response removed -> not ready (technical).
    sp.put(D.format(pid) + "technical", json={"message": ""})
    assert _sections(sp, pid)[:2] == (False, ["technical"])
    sp.put(D.format(pid) + "technical", json={"message": "Method."})
    # 4. Required document removed -> not ready (documents).
    doc = sp.get(f"/projects/{pid}/offers/documents").json()[0]["id"]
    sp.delete(f"/projects/{pid}/offers/documents/{doc}")
    assert _sections(sp, pid)[:2] == (False, ["documents"])
    # Declarations: only the requirement's own; withdrawn acceptance -> not ready.
    assert sp.put(D.format(pid) + "declarations", json={"accepted_declarations": ["Something else"]}).status_code == 400
    sp.put(D.format(pid) + "declarations", json={"accepted_declarations": []})
    assert "declarations" in _sections(sp, pid)[1]
    assert db.query(Offer).one().status == OfferStatus.draft  # checking never submits


def test_a_simple_requirement_asks_only_for_what_it_needs(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)  # no response rules beyond the price
    sp.post(f"/projects/{pid}/participate")
    assert _sections(sp, pid)[:2] == (False, ["price"])
    sp.put(D.format(pid) + "commercial", json={"amount": "900"})
    assert _sections(sp, pid)[:2] == (True, [])


def test_per_item_pricing_must_cover_every_item(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = owner.post("/projects", data={"title": "BOQ", "address": "x", "description": "d", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [{"description": "A", "quantity": "2"}, {"description": "B"}]})
    owner.post(f"/owner/projects/{pid}/publish")
    sp.post(f"/projects/{pid}/participate")
    a, b = sorted(db.get(Project, pid).items, key=lambda i: i.position)
    sp.put(D.format(pid) + "commercial", json={"item_prices": [{"item_id": a.id, "rate": "5"}]})
    _, sections, issues = _sections(sp, pid)
    assert sections == ["price"] and "every item" in issues[0]["message"]
    sp.put(D.format(pid) + "commercial", json={"item_prices": [{"item_id": a.id, "rate": "5"}, {"item_id": b.id, "rate": "7"}]})
    assert _sections(sp, pid)[:2] == (True, [])


def test_invalid_timing_ineligibility_and_lifecycle_block_it(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    pid = _demanding(owner, eligibility={"match_governorate": True})
    sp.post(f"/projects/{pid}/participate")
    _complete(sp, pid)
    assert _sections(sp, pid)[:2] == (True, [])
    # 5. The deadline is extended past the committed start: the saved timing is no longer valid.
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(25)}, headers={"If-Match": str(v)}).status_code == 200
    ready, sections, issues = _sections(sp, pid)
    assert not ready and sections == ["timing"] and "before the response deadline" in issues[0]["message"]
    # ...and submitting directly is refused for the same reason (12).
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "12500", "message": "m", "accepted_declarations": [DECL]}).status_code == 400
    sp.put(D.format(pid) + "timing", json={"proposed_start_date": _d(30), "proposed_duration_days": 30})
    assert _sections(sp, pid)[0] is True
    # 8. The provider stops serving the requirement's governorate: not eligible any more.
    sp.put("/service-provider/services", json={"categories": [], "governorates": ["jahra"]})
    ready, sections, _ = _sections(sp, pid)
    assert not ready and sections == ["eligibility"]
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "12500", "message": "m", "accepted_declarations": [DECL]}).status_code == 403
    sp.put("/service-provider/services", json={"categories": [], "governorates": ["hawalli"]})
    # Access lapses: named too.
    profile = db.query(ServiceProviderProfile).one()
    profile.payment_override_active = False
    db.commit()
    assert _sections(sp, pid)[1] == ["account"]
    profile.payment_override_active = True
    db.commit()
    assert _sections(sp, pid)[0] is True
    # 9. Suspended / paused by the owner after preparation: blocked.
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True})
    assert _sections(sp, pid)[1] == ["requirement"]
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": False})
    # 10. The deadline passes (server clock): blocked, and said so; submission refused.
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    ready, sections, issues = _sections(sp, pid)
    assert not ready and "requirement" in sections and any("deadline has passed" in i["message"] for i in issues)
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "12500", "message": "m", "accepted_declarations": [DECL]}).status_code == 400
    assert db.query(Offer).one().status == OfferStatus.draft


def test_amendment_and_closure_after_a_ready_check(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid, closing = _demanding(owner, "Amended"), _demanding(owner, "Cancelled")
    for p in (pid, closing):
        sp.post(f"/projects/{p}/participate")
        _complete(sp, p)
        assert _sections(sp, p)[0] is True
    # 11. A material amendment: the ready result no longer holds; submitting against the old version is refused.
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "HV works plus a second transformer."}, headers={"If-Match": str(v)})
    ready, sections, issues = _sections(sp, pid)
    assert not ready and sections == ["requirement"] and "Review the current requirement" in issues[0]["message"]
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "12500", "message": "m", "accepted_declarations": [DECL]}).status_code == 409
    sp.post(f"/projects/{pid}/participate")  # reviewed
    assert _sections(sp, pid)[0] is True
    # 9. Cancelled after a "ready" check: the earlier result grants nothing.
    owner.post(f"/owner/projects/{closing}/cancel", json={"reason": "not_needed"})
    assert _sections(sp, closing)[:2] == (False, ["requirement"])
    assert sp.post(f"/projects/{closing}/offers", json={"amount": "12500", "message": "m", "accepted_declarations": [DECL]}).status_code == 400


def test_direct_submission_still_enforces_the_rules_and_the_gate_is_private(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com")
    pid = _demanding(owner)
    sp.post(f"/projects/{pid}/participate")
    # 12. Straight to the submission API with the parts missing: refused, still a draft.
    r = sp.post(f"/projects/{pid}/offers", json={"amount": "12500"})
    assert r.status_code == 400 and "missing" in r.json()["detail"]
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "0", "message": "m", "timeline_estimate": "4 weeks", "accepted_declarations": [DECL]}).status_code == 400
    assert db.query(Offer).one().status == OfferStatus.draft and owner.get(f"/owner/projects/{pid}/offers").json() == []
    # The gate is about one's own offer: a competitor with no offer is told to start one, not shown this one.
    _, sections, _ = _sections(rival, pid)
    assert sections == ["offer"]
    # A requirement that isn't published: not found. Arabic: translated.
    draft = owner.post("/projects", data={"title": "Draft", "address": "x", "bid_deadline": _when(9)}).json()["id"]
    assert sp.get(CHECK.format(draft)).status_code == 404
    ar = sp.get(CHECK.format(pid), headers={"Accept-Language": "ar"}).json()
    assert all(i["message"] and not i["message"].startswith("Your offer") for i in ar["issues"])

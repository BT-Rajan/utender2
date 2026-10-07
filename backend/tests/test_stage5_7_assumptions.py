"""Stage 5.7: the provider's assumptions, exclusions, qualifications and
offer clarifications (offers.assumptions) -- saved on the offer draft without
submitting, beside everything else on it; kept exactly as written for the
owner to weigh once submitted; private to the provider's side; separate
from questions about the requirement (Stage 4.7)."""
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.clarification import Clarification
from app.models.enums import OfferStatus
from app.models.offer import Offer, OfferDocument
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _when

ASSUME = "/projects/{}/offers/draft/assumptions"
TEXT = "Assumes the owner provides water and power on site.\nExcludes dewatering.\nProposes LSZH cable in place of PVC -- needs owner acceptance."


def _published(owner, title="Rewiring"):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Rewire a villa.", "bid_deadline": _when(10), "expected_start_date": (datetime.utcnow() + timedelta(days=20)).date().isoformat()}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"documents": [{"name": "Method statement", "required": False}]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def test_saved_beside_the_rest_of_the_draft_and_edited_later(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _published(owner)
    draft = sp.post(f"/projects/{pid}/participate").json()["offer_id"]
    start = (datetime.utcnow() + timedelta(days=21)).date().isoformat()
    sp.put(f"/projects/{pid}/offers/draft/commercial", json={"amount": "900"})
    sp.put(f"/projects/{pid}/offers/draft/technical", json={"message": "Method."})
    sp.put(f"/projects/{pid}/offers/draft/timing", json={"proposed_start_date": start, "proposed_duration_days": 30})
    sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("m.pdf", b"%PDF", "application/pdf")})
    r = sp.put(ASSUME.format(pid), json={"assumptions": TEXT}, headers={"If-Match": "3"})
    assert r.status_code == 200, r.text
    saved = r.json()
    # Kept exactly as written; nothing else on the draft changed; not submitted.
    assert (saved["id"], saved["status"], saved["assumptions"]) == (draft, "draft", TEXT)
    assert (Decimal(saved["amount"]), saved["message"], saved["proposed_start_date"], saved["proposed_duration_days"], [d["label"] for d in saved["documents"]]) == (
        Decimal("900"), "Method.", start, 30, ["Method statement"])
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    # Leave and return; edit; a later save of another part leaves it alone.
    assert sp.get(f"/projects/{pid}/offers/mine").json()["assumptions"] == TEXT
    assert sp.put(ASSUME.format(pid), json={"assumptions": "Excludes dewatering."}).json()["assumptions"] == "Excludes dewatering."
    assert sp.put(f"/projects/{pid}/offers/draft/technical", json={"message": "Method v2."}).json()["assumptions"] == "Excludes dewatering."
    # Optional, bounded, text only.
    assert sp.put(ASSUME.format(pid), json={"assumptions": "  "}).json()["assumptions"] is None
    assert sp.put(ASSUME.format(pid), json={"assumptions": "x" * 10_001}).status_code == 422
    assert sp.put(ASSUME.format(pid), json={"assumptions": ["a"]}).status_code == 422
    # Once submitted the owner receives them as written; a revision keeps the earlier wording.
    sp.put(ASSUME.format(pid), json={"assumptions": TEXT})
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "900", "message": "Method v2.", "assumptions": TEXT}).status_code == 200
    assert owner.get(f"/owner/projects/{pid}/offers").json()[0]["assumptions"] == TEXT
    sp.post(f"/projects/{pid}/offers", json={"amount": "880", "message": "Method v2.", "assumptions": "Excludes dewatering only."})
    assert [h["assumptions"] for h in sp.get(f"/projects/{pid}/offers/mine/history").json()] == [TEXT]


def test_private_separate_from_questions_and_never_the_requirement(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    rival = _account(db, "service_provider", "rival@example.com")
    pid, other = _published(owner, "Villa"), _published(owner, "Warehouse")
    boss.post(f"/projects/{pid}/participate")
    before = owner.get(f"/projects/{pid}").json()
    assert eng.put(ASSUME.format(pid), json={"assumptions": "Org conditions.", "description": "Hacked", "title": "Hacked"}, headers={"If-Match": "0"}).status_code == 200
    assert boss.put(ASSUME.format(pid), json={"assumptions": "Stale tab."}, headers={"If-Match": "0"}).status_code == 409
    after = owner.get(f"/projects/{pid}").json()
    assert {k: after[k] for k in ("title", "description", "version")} == {k: before[k] for k in ("title", "description", "version")}
    offer = db.query(Offer).one()
    assert rival.put(ASSUME.format(pid), json={"assumptions": "Hijack", "offer_id": offer.id, "organization_id": offer.organization_id}).status_code == 404
    assert rival.get(f"/projects/{pid}/offers/mine").json() is None
    assert boss.put(ASSUME.format(other), json={"assumptions": "Elsewhere"}).status_code == 404
    # Not a question about the requirement: nothing reaches Q&A, and the owner sees nothing of the draft.
    assert db.query(Clarification).count() == 0 and owner.get(f"/projects/{pid}/clarifications").json() == []
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    db.expire_all()
    assert db.query(Offer).one().assumptions == "Org conditions."


def test_amendments_and_endings(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    amended, suspended, expiring = (_published(owner, t) for t in ("Amended", "Suspended", "Expiring"))
    for pid in (amended, suspended, expiring):
        sp.post(f"/projects/{pid}/participate")
        sp.put(ASSUME.format(pid), json={"assumptions": "v0 conditions."})
    v = owner.get(f"/projects/{amended}").json()["version"]
    owner.patch(f"/projects/{amended}", json={"description": "Rewire a villa: 40 points plus 6 outdoor."}, headers={"If-Match": str(v)})
    r = sp.put(ASSUME.format(amended), json={"assumptions": "v1 conditions."})
    assert r.status_code == 409 and "Review the current requirement" in r.json()["detail"]
    sp.post(f"/projects/{amended}/participate")
    saved = sp.put(ASSUME.format(amended), json={"assumptions": "v1 conditions."}).json()
    assert (saved["assumptions"], saved["based_on_material_revision"]) == ("v1 conditions.", 1)
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})
    db.get(Project, expiring).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    for pid in (suspended, expiring):
        assert sp.put(ASSUME.format(pid), json={"assumptions": "late"}).status_code == 400
    db.expire_all()
    assert {o.assumptions for o in db.query(Offer).filter(Offer.project_id != amended)} == {"v0 conditions."}
    assert all(o.status == OfferStatus.draft for o in db.query(Offer)) and db.query(OfferDocument).count() == 0

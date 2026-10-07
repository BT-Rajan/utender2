"""Stage 5.4: the technical response -- the requirement's "technical approach /
method" (Stage 3.8) -- saved on the offer draft without submitting, beside
the price from 5.3, private to the provider's side, never reaching the
requirement, and refused against an outdated requirement version, a stale
page or a requirement no longer accepting offers."""
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.enums import OfferStatus
from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _publish, _when

TECH = "/projects/{}/offers/draft/technical"
PRICE = "/projects/{}/offers/draft/commercial"
APPROACH = "Method: isolate per floor, chase and conduit, 2.5mm LSZH to BS 7671.\n\nDeliverables: test certificates, as-built drawings."


def _approach_required(owner, title="Rewiring, approach required"):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Rewire a villa.", "bid_deadline": _when(10)}).json()["id"]
    assert owner.put(f"/projects/{pid}/response-requirements", json={"approach": "required"}).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def test_technical_response_saved_beside_the_price_and_edited_later(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _approach_required(owner)
    draft = sp.post(f"/projects/{pid}/participate").json()["offer_id"]
    sp.put(PRICE.format(pid), json={"amount": "900"}, headers={"If-Match": "0"})
    # Saved without submitting; the price from 5.3 is untouched. Line breaks kept.
    r = sp.put(TECH.format(pid), json={"message": APPROACH}, headers={"If-Match": "1"})
    assert r.status_code == 200, r.text
    assert (r.json()["id"], r.json()["status"], r.json()["message"], Decimal(r.json()["amount"]), r.json()["draft_version"]) == (draft, "draft", APPROACH, Decimal("900"), 2)
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    # Leave and return: the same response on the same draft.
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["id"], mine["message"], mine["status"]) == (draft, APPROACH, "draft")
    # Edit; a later price save leaves the technical response alone.
    assert sp.put(TECH.format(pid), json={"message": "Revised method."}).json()["message"] == "Revised method."
    assert sp.put(PRICE.format(pid), json={"amount": "950"}).json()["message"] == "Revised method."
    # A draft may have none yet, even where the requirement makes it mandatory (that's checked on submission).
    assert sp.put(TECH.format(pid), json={"message": "   "}).json()["message"] is None
    assert sp.put(TECH.format(pid), json={"message": "x" * 10_001}).status_code == 422
    assert sp.put(TECH.format(pid), json={"message": 42}).status_code == 422
    # The requirement's own rule still applies when the offer is submitted.
    r = sp.post(f"/projects/{pid}/offers", json={"amount": "950"})
    assert r.status_code == 400 and "technical approach" in r.json()["detail"]
    assert db.query(Offer).one().status == OfferStatus.draft


def test_only_the_providers_own_draft_and_never_the_requirement(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    rival = _account(db, "service_provider", "rival@example.com")
    pid, other = _publish(owner, "Villa"), _publish(owner, "Warehouse")
    boss.post(f"/projects/{pid}/participate")
    before = owner.get(f"/projects/{pid}").json()
    # A colleague continues the organization's draft; a stale tab is refused, not overwritten.
    assert eng.put(TECH.format(pid), json={"message": "Org method."}, headers={"If-Match": "0"}).status_code == 200
    r = boss.put(TECH.format(pid), json={"message": "Older tab."}, headers={"If-Match": "0"})
    assert r.status_code == 409 and "changed somewhere else" in r.json()["detail"]
    # Another provider, with the organization's ids in the body, or another requirement: nothing to save into.
    offer = db.query(Offer).one()
    assert rival.put(TECH.format(pid), json={"message": "Hijack", "offer_id": offer.id, "service_provider_id": offer.service_provider_id, "organization_id": offer.organization_id}).status_code == 404
    assert rival.get(f"/projects/{pid}/offers/mine").json() is None
    assert boss.put(TECH.format(other), json={"message": "Wrong requirement"}).status_code == 404
    # Requirement fields sent to the offer API change nothing on the requirement.
    boss.put(TECH.format(pid), json={"message": "Mine.", "description": "Hacked scope", "title": "Hacked", "pricing_basis": "per_item"})
    after = owner.get(f"/projects/{pid}").json()
    assert {k: after[k] for k in ("title", "description", "pricing_basis", "items", "version")} == {k: before[k] for k in ("title", "description", "pricing_basis", "items", "version")}
    db.expire_all()
    assert db.query(Offer).count() == 1 and db.query(Offer).one().message == "Mine."


def test_requirement_changes_while_preparing(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    amended, suspended, expiring, canceled = (_publish(owner, t) for t in ("Amended", "Suspended", "Expiring", "Canceled"))
    for pid in (amended, suspended, expiring, canceled):
        sp.post(f"/projects/{pid}/participate")
        assert sp.put(TECH.format(pid), json={"message": "Method v0."}).status_code == 200
    # A material amendment: no response is saved against the old version until the current one has been reviewed.
    v = owner.get(f"/projects/{amended}").json()["version"]
    owner.patch(f"/projects/{amended}", json={"description": "Rewire a villa: 40 points plus 6 outdoor."}, headers={"If-Match": str(v)})
    r = sp.put(TECH.format(amended), json={"message": "Method v1."})
    assert r.status_code == 409 and "Review the current requirement" in r.json()["detail"]
    assert db.query(Offer).filter(Offer.project_id == amended).one().based_on_material_revision == 0
    sp.post(f"/projects/{amended}/participate")
    saved = sp.put(TECH.format(amended), json={"message": "Method v1."}).json()
    assert (saved["message"], saved["based_on_material_revision"]) == ("Method v1.", 1)
    # Suspended, past its deadline, ended: kept as it was, but no longer editable.
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})
    db.get(Project, expiring).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.post(f"/owner/projects/{canceled}/cancel", json={"reason": "not_needed"})
    for pid in (suspended, expiring, canceled):
        assert sp.put(TECH.format(pid), json={"message": "Late change."}).status_code == 400, pid
    db.expire_all()
    assert {o.message for o in db.query(Offer).filter(Offer.project_id != amended)} == {"Method v0."}
    assert all(o.status == OfferStatus.draft for o in db.query(Offer))

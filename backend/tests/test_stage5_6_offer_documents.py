"""Stage 5.6: documents supporting an offer -- the ones the requirement asks
for (Stage 3.8) -- attached to the provider's own offer draft through the
existing private storage, without submitting; tied to the offer, the
requirement version and the person who supplied them; reachable only by the
provider's side (and the owner once the offer is submitted and unsealed);
and kept, not lost, when the requirement changes or ends."""
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from app.models.enums import OfferStatus
from app.models.offer import Offer, OfferDocument
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _when

DOCS = "/projects/{}/offers/documents"
RULES = {"documents": [{"name": "Method statement", "required": True}, {"name": "Product data", "required": False}]}


def _get(client, url):
    return client.get("/" + url.split("://", 1)[-1].split("/", 1)[-1])


def _signed(client, url):
    """Stage 6.2: the one-minute signed link an authorised click is sent on to."""
    r = client.get("/" + url.split("://", 1)[-1].split("/", 1)[-1], follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"]


def _asking(owner, title="Rewiring with documents"):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Rewire a villa.", "bid_deadline": _when(10)},
                     files=[("drawings", ("plan.pdf", b"%PDF-owner", "application/pdf"))]).json()["id"]
    assert owner.put(f"/projects/{pid}/response-requirements", json=RULES).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _upload(client, pid, label="Method statement", name="method.pdf", content=b"%PDF-method"):
    return client.post(DOCS.format(pid), data={"label": label}, files={"file": (name, content, "application/pdf")})


def test_attach_view_replace_remove_on_the_draft(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _asking(owner)
    draft = sp.post(f"/projects/{pid}/participate").json()["offer_id"]
    sp.put(f"/projects/{pid}/offers/draft/commercial", json={"amount": "900"})
    sp.put(f"/projects/{pid}/offers/draft/technical", json={"message": "Method."})
    me = sp.get("/auth/me").json()["id"]
    # Upload: attached to this draft, not submitted; the rest of the draft intact.
    r = _upload(sp, pid)
    assert r.status_code == 200, r.text
    assert [(d["label"], d["file_name"], d["material_revision"]) for d in r.json()] == [("Method statement", "method.pdf", 0)]
    doc = db.query(OfferDocument).one()
    assert (doc.offer_id, doc.project_id, doc.service_provider_id, doc.organization_id, doc.uploaded_by) == (draft, pid, me, None, me)
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["status"], Decimal(mine["amount"]), mine["message"], [d["label"] for d in mine["documents"]]) == ("draft", Decimal("900"), "Method.", ["Method statement"])
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    # Leave and return: still there, and openable under its real name, from a fresh, short-lived link.
    url = _signed(sp, sp.get(DOCS.format(pid)).json()[0]["url"])
    query = parse_qs(urlparse(url).query)
    assert query["name"] == ["method.pdf"] and int(query["exp"][0]) - datetime.utcnow().timestamp() <= 60 + 5
    got = _get(sp, url)
    assert got.status_code == 200 and got.content == b"%PDF-method" and "method.pdf" in got.headers["content-disposition"]
    # The name is signed in: a re-labelled link is refused.
    assert _get(sp, url.replace("name=method.pdf", "name=evil.html")).status_code == 403
    # Replace (same label): one document, the new file; then add a second, remove it.
    _upload(sp, pid, name="method-v2.pdf", content=b"%PDF-v2")
    assert db.query(OfferDocument).count() == 1 and _get(sp, sp.get(DOCS.format(pid)).json()[0]["url"]).content == b"%PDF-v2"
    other = _upload(sp, pid, label="Product data", name="data.pdf").json()
    extra = next(d["id"] for d in other if d["label"] == "Product data")
    assert [d["label"] for d in sp.delete(f"{DOCS.format(pid)}/{extra}").json()] == ["Method statement"]
    # Only what the requirement asks for, in allowed types, not empty.
    assert _upload(sp, pid, label="Bank statement").status_code == 400
    assert sp.post(DOCS.format(pid), data={"label": "Method statement"}, files={"file": ("run.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert sp.post(DOCS.format(pid), data={"label": "Method statement"}, files={"file": ("m.pdf", b"", "application/pdf")}).status_code == 400
    assert db.query(Offer).one().status == OfferStatus.draft


def test_requirement_and_offer_documents_stay_separate_and_private(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com", organization="Rival Co")
    pid, other = _asking(owner, "Villa"), _asking(owner, "Warehouse")
    sp.post(f"/projects/{pid}/participate")
    rival.post(f"/projects/{pid}/participate")
    _upload(sp, pid, content=b"%PDF-noor")
    _upload(rival, pid, content=b"%PDF-rival")
    noor_doc = db.query(OfferDocument).filter(OfferDocument.organization_id.is_(None)).one()
    # Each side sees only its own; the owner's requirement documents are not among them, nor theirs among the owner's.
    assert [d["file_name"] for d in sp.get(DOCS.format(pid)).json()] == ["method.pdf"]
    assert _get(rival, rival.get(DOCS.format(pid)).json()[0]["url"]).content == b"%PDF-rival"
    assert [d["file_name"] for d in sp.get(f"/projects/{pid}").json()["drawings"]] == ["plan.pdf"]
    assert all(d.label != "plan.pdf" for d in db.query(OfferDocument))
    # Another side's document id, another requirement's path: refused, nothing removed.
    assert rival.delete(f"{DOCS.format(pid)}/{noor_doc.id}").status_code == 404
    assert sp.delete(f"{DOCS.format(other)}/{noor_doc.id}").status_code == 404
    assert sp.get(DOCS.format(other)).json() == []
    # Ids in the form are ignored: the server decides whose offer it belongs to.
    rival_offer = db.query(Offer).filter(Offer.organization_id.isnot(None)).one()
    sp.post(DOCS.format(pid), data={"label": "Product data", "offer_id": rival_offer.id, "organization_id": rival_offer.organization_id},
            files={"file": ("d.pdf", b"%PDF-d", "application/pdf")})
    added = db.query(OfferDocument).filter(OfferDocument.label == "Product data").one()
    assert added.organization_id is None and added.offer_id == noor_doc.offer_id
    # A forged link to another side's file: refused.
    rival_path = _signed(rival, rival.get(DOCS.format(pid)).json()[0]["url"]).split("/files/offer-documents/")[1].split("?")[0]
    forged = _signed(sp, sp.get(DOCS.format(pid)).json()[0]["url"]).replace(noor_doc.file_path, rival_path)
    # Nor does another side's document id open through one's own route.
    rival_doc = db.query(OfferDocument).filter(OfferDocument.organization_id.isnot(None)).one()
    assert sp.get(f"{DOCS.format(pid)}/{rival_doc.id}/file", follow_redirects=False).status_code == 404
    assert _get(sp, forged).status_code == 403
    # A draft's documents aren't the owner's to see; once submitted (owner-visible), they are.
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    sp.put(f"/projects/{pid}/offers/draft/commercial", json={"amount": "900"})
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 200
    seen = owner.get(f"/owner/projects/{pid}/offers").json()[0]
    assert sorted(d["file_name"] for d in seen["documents"]) == ["d.pdf", "method.pdf"]
    assert _get(owner, next(d["url"] for d in seen["documents"] if d["file_name"] == "method.pdf")).content == b"%PDF-noor"


def test_amendments_and_endings_keep_the_documents_and_their_context(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    amended, suspended, expiring, canceled, extended = (_asking(owner, t) for t in ("Amended", "Suspended", "Expiring", "Canceled", "Extended"))
    for pid in (amended, suspended, expiring, canceled, extended):
        sp.post(f"/projects/{pid}/participate")
        assert _upload(sp, pid).status_code == 200
    # The owner replaces their drawing (a material change): the provider gets the current one, the
    # version they responded to is still on record, and their own document keeps its version.
    owner.post(f"/projects/{amended}/drawings", files=[("drawings", ("plan.pdf", b"%PDF-owner-v2", "application/pdf"))])
    assert _get(sp, sp.get(f"/projects/{amended}").json()["drawings"][0]["url"]).content == b"%PDF-owner-v2"
    v0 = sp.get(f"/projects/{amended}/versions/0").json()["documents"]
    assert _get(sp, v0[0]["url"]).content == b"%PDF-owner"
    # No new document on the old version until the current one is reviewed; then it records the new one.
    assert _upload(sp, amended, label="Product data").status_code == 409
    sp.post(f"/projects/{amended}/participate")
    docs = _upload(sp, amended, label="Product data", name="data.pdf").json()
    assert {d["label"]: d["material_revision"] for d in docs} == {"Method statement": 0, "Product data": 1}
    # Extended: the same documents on the same offer.
    v = owner.get(f"/projects/{extended}").json()["version"]
    owner.patch(f"/projects/{extended}", json={"bid_deadline": _when(20)}, headers={"If-Match": str(v)})
    assert [d["file_name"] for d in sp.get(DOCS.format(extended)).json()] == ["method.pdf"]
    # Suspended, past its deadline, ended: kept and still the provider's to open, but not changeable.
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})
    db.get(Project, expiring).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.post(f"/owner/projects/{canceled}/cancel", json={"reason": "not_needed"})
    for pid in (suspended, expiring, canceled):
        listed = sp.get(DOCS.format(pid)).json()
        assert [d["file_name"] for d in listed] == ["method.pdf"] and _get(sp, listed[0]["url"]).content == b"%PDF-method"
        assert _upload(sp, pid, name="late.pdf").status_code == 400
        assert sp.delete(f"{DOCS.format(pid)}/{listed[0]['id']}").status_code == 400
    assert db.query(OfferDocument).count() == 6


def test_an_organization_shares_its_offer_documents(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    pid = _asking(owner)
    boss.post(f"/projects/{pid}/participate")
    _upload(eng, pid)
    _upload(boss, pid, name="method-final.pdf", content=b"%PDF-final")  # replaces the organization's, not a second one
    doc = db.query(OfferDocument).one()
    assert (doc.file_name, doc.uploaded_by, doc.offer_id) == ("method-final.pdf", boss.get("/auth/me").json()["id"], db.query(Offer).one().id)
    assert [d["file_name"] for d in eng.get(DOCS.format(pid)).json()] == ["method-final.pdf"]
    assert eng.delete(f"{DOCS.format(pid)}/{doc.id}").status_code == 200 and db.query(OfferDocument).count() == 0

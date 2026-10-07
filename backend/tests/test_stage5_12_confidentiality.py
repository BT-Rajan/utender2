"""Stage 5.12: sealed offer / confidentiality integrity. Once Provider A has
submitted, nothing of A's offer -- price, items, method, timing, assumptions,
documents, even who A is -- reaches another provider, an unrelated owner or
an unverified account, through ANY read route of the API, with ANY id they
might know or guess, at any point in the requirement's life. The owner gets
it only through the owner workflow (and a sealed tender only after its
deadline); A keeps their own; admin oversight is as before."""
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi.routing import APIRoute

from app.main import app
from app.models.offer import Offer, OfferDocument
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _when

# Everything only Provider A (and, when permitted, the owner) may ever see.
MARKERS = ("98765.432", "SECRET-METHOD-A7", "SECRET-ASSUME-A7", "SECRET-PERIOD-A7", "secret-a7-method.pdf", "alphasecret")
DECL = "I have visited the site."


def _tender(owner, sealed=True, title="HV works"):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Substation.", "bid_deadline": _when(10),
                                       "tender_type": "sealed" if sealed else "owner_visible"}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"approach": "required", "documents": [{"name": "Method statement", "required": True}], "declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _submit(sp, pid, amount, method, assumptions="", period="", doc=("m.pdf", b"%PDF")):
    sp.post(f"/projects/{pid}/participate")
    assert sp.put(f"/projects/{pid}/offers/draft", json={"amount": amount, "message": method, "assumptions": assumptions, "timeline_estimate": period, "accepted_declarations": [DECL]}).status_code == 200
    assert sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": (doc[0], doc[1], "application/pdf")}).status_code == 200
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code == 200, r.text
    return r.json()


def _get_routes():
    return sorted({r.path for r in app.routes if isinstance(r, APIRoute) and "GET" in r.methods and not r.path.startswith("/files/")})


def _sweep(client, ids: dict) -> list[str]:
    """Every GET route, with every id a caller could know or guess put in
    every path parameter; returns any response that carries one of A's
    markers."""
    leaks = []
    for path in _get_routes():
        params = [p.split("}")[0].split(":")[0] for p in path.split("{")[1:]]
        candidates = [path]
        for name in params:
            values = ids.get(name, ids["any"])
            candidates = [c.replace("{" + name + "}", quote(str(v), safe="")) for c in candidates for v in values]
        for url in candidates:
            r = client.get(url, params={"role": "service_provider"})
            body = r.text
            leaks += [f"{url} -> {m}" for m in MARKERS if m in body]
    return leaks


def _parties(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "alphasecret@example.com")
    b = _account(db, "service_provider", "bravo@example.com", organization="Bravo Co")
    stranger_owner = _account(db, "owner", "stranger@example.com")
    unverified = _account(db, "service_provider", "pending@example.com", approve=False)
    return owner, a, b, stranger_owner, unverified


def _ids(db, pid, a, b):
    a_offer = db.query(Offer).filter(Offer.project_id == pid, Offer.organization_id.is_(None)).one()
    doc = db.query(OfferDocument).filter(OfferDocument.offer_id == a_offer.id).one()
    a_id = a.get("/auth/me").json()["id"]
    b_offer = db.query(Offer).filter(Offer.project_id == pid, Offer.organization_id.isnot(None)).first()
    every = [pid, a_offer.id, doc.id, a_id, a_offer.organization_id or a_id, "0", "1"] + ([b_offer.id] if b_offer else [])
    return {
        "project_id": [pid], "offer_id": [a_offer.id] + ([b_offer.id] if b_offer else []), "service_provider_id": [a_id], "owner_id": [a_id],
        "number": [0, 1], "token": ["x"], "any": every,
    }, a_offer, doc


def test_no_route_gives_another_party_any_part_of_a_submitted_offer(db):
    owner, a, b, stranger_owner, unverified = _parties(db)
    pid = _tender(owner, sealed=True)
    _submit(a, pid, "98765.432", "SECRET-METHOD-A7", "SECRET-ASSUME-A7", "SECRET-PERIOD-A7", ("secret-a7-method.pdf", b"%PDF-A7"))
    _submit(b, pid, "11111", "Bravo method")  # a competitor on the same requirement
    ids, a_offer, doc = _ids(db, pid, a, b)
    # 2/3/4/9/11. Through every read route, with every id: nothing of A's offer, nested or not.
    for who, client in (("competitor", b), ("unrelated owner", stranger_owner), ("unverified provider", unverified)):
        assert _sweep(client, ids) == [], who
    # The sweep does find the markers where they belong (it isn't blind): A's own routes.
    assert any("SECRET-METHOD-A7" in leak for leak in _sweep(a, ids))
    # 2. The competitor still sees the opportunity itself.

    assert b.get(f"/projects/{pid}").status_code == 200
    # 6. A sees their own, in full.
    mine = a.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["amount"], mine["message"], mine["assumptions"], mine["documents"][0]["file_name"]) == ("98765.432", "SECRET-METHOD-A7", "SECRET-ASSUME-A7", "secret-a7-method.pdf")
    # 12. Sealed and open: even the owner sees that offers are in, not what they say or whose they are.
    listed = owner.get(f"/owner/projects/{pid}/offers").json()
    assert len(listed) == 2 and not any(m in str(listed) for m in MARKERS)
    assert owner.get(f"/owner/projects/{pid}/offers/{a_offer.id}/history").status_code == 404
    # 8. An unrelated owner gets nothing of these offers.
    assert stranger_owner.get(f"/owner/projects/{pid}/offers").status_code == 404
    # 5. A's document: no signed link is ever issued to B, and a forged or re-pointed one is refused.
    local = lambda url: "/" + url.split("://", 1)[-1].split("/", 1)[-1]  # noqa: E731
    path = local(mine["documents"][0]["url"])
    # Stage 6.2: a document link is an authorised route; B's own sends B on to a one-minute signed link.
    b_path = local(b.get(local(b.get(f"/projects/{pid}/offers/documents").json()[0]["url"]), follow_redirects=False).headers["location"])
    # A's document id through B's route, or the owner's route: not found.
    assert b.get(path, follow_redirects=False).status_code == 404
    assert b.get(f"/owner/projects/{pid}/offers/{a_offer.id}/documents/file", params={"label": "Method statement"}).status_code == 403
    b_key = b_path.split("/files/offer-documents/")[1].split("?")[0]
    forged = b_path.replace(b_key, doc.file_path)  # B's own valid signature, pointed at A's file
    assert b.get(forged).status_code == 403 and "%PDF-A7" not in b.get(forged).text
    unsigned = f"/files/offer-documents/{doc.file_path}"
    assert b.get(unsigned).status_code == 422 or b.get(unsigned).status_code == 403
    assert a.get(path).content == b"%PDF-A7"  # the owner of the file, with the link they were given
    # Admin oversight is unchanged: the platform operator sees offers (sealed included), by design.
    admin = _admin(db)
    assert any(o["id"] == a_offer.id and o["amount"] == "98765.432" for o in admin.get("/admin/offers").json())


def test_every_lifecycle_state_keeps_offers_from_competitors(db):
    owner, a, b, stranger_owner, unverified = _parties(db)
    admin = _admin(db)
    pids = {state: _tender(owner, sealed=(state != "visible"), title=state) for state in ("visible", "suspended", "extended", "amended", "expired", "canceled", "ended_early")}
    for pid in pids.values():
        _submit(a, pid, "98765.432", "SECRET-METHOD-A7", "SECRET-ASSUME-A7", "SECRET-PERIOD-A7", ("secret-a7-method.pdf", b"%PDF-A7"))
        _submit(b, pid, "11111", "Bravo method")
    admin.post(f"/admin/projects/{pids['suspended']}/suspend", json={"suspended": True})
    v = owner.get(f"/projects/{pids['extended']}").json()["version"]
    owner.patch(f"/projects/{pids['extended']}", json={"bid_deadline": _when(20)}, headers={"If-Match": str(v)})
    v = owner.get(f"/projects/{pids['amended']}").json()["version"]
    owner.patch(f"/projects/{pids['amended']}", json={"description": "Substation, plus a second bay."}, headers={"If-Match": str(v)})
    db.get(Project, pids["expired"]).bid_deadline = datetime.utcnow() - timedelta(seconds=1)  # 10. closed at its deadline
    db.commit()
    owner.post(f"/owner/projects/{pids['canceled']}/cancel", json={"reason": "not_needed"})
    assert owner.post(f"/owner/projects/{pids['ended_early']}/close-externally", json={}).status_code == 200
    a.get("/service-provider/feed")  # any read syncs the deadline
    db.expire_all()
    reached = {state: (db.get(Project, pid).status.value, db.get(Project, pid).is_suspended) for state, pid in pids.items()}
    assert reached == {
        "visible": ("open", False), "suspended": ("open", True), "extended": ("open", False), "amended": ("open", False),
        "expired": ("closed", False), "canceled": ("canceled", False), "ended_early": ("no_award", False),
    }, reached
    for state, pid in pids.items():
        ids, a_offer, _ = _ids(db, pid, a, b)
        for who, client in (("competitor", b), ("unrelated owner", stranger_owner), ("unverified provider", unverified)):
            assert _sweep(client, ids) == [], (state, who)
        # A still has their own.
        assert a.get(f"/projects/{pid}/offers/mine").json()["message"] == "SECRET-METHOD-A7", state
    # The owner: owner-visible from the start; sealed only once its deadline has passed --
    # ending a sealed tender early (cancelled, ended without award) never opens it.
    owner_view = {state: owner.get(f"/owner/projects/{pid}/offers").json() for state, pid in pids.items()}
    assert "98765.432" in str(owner_view["visible"]) and "98765.432" in str(owner_view["expired"])
    assert any("98765.432" in leak for leak in _sweep(owner, _ids(db, pids["visible"], a, b)[0]))  # the sweep sees what the owner may see
    for state in ("suspended", "extended", "amended", "canceled", "ended_early"):
        assert not any(m in str(owner_view[state]) for m in MARKERS), state

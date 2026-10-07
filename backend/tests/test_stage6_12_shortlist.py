"""Stage 6.12: shortlist. While evaluating, the owner's side marks promising
offers -- several if they like -- privately, without awarding anything or
touching the offers; only live offers on their own requirement; repeatable
safely; frozen once the outcome is recorded."""
from app.models.audit_log import AuditLog
from app.models.enums import ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.offer_shortlist import OfferShortlist
from app.models.project import Project
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender


def _offer_id(db, pid, sp):
    me = sp.get("/auth/me").json()["id"]
    return db.query(Offer).filter(Offer.project_id == pid, Offer.service_provider_id == me).one().id


def _closed(db, owner, *providers, title="HV works"):
    pid = _tender(owner, title)
    for sp in providers:
        _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    return pid


def test_several_offers_shortlisted_privately_and_nothing_else_changes(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana"))
    pid = _closed(db, owner, a, b, c)
    a_offer, b_offer = _offer_id(db, pid, a), _offer_id(db, pid, b)
    before = {o.id: (o.status, o.amount, o.message, o.revision, o.updated_at) for o in db.query(Offer)}
    notes_before = db.query(Notification).count()
    for offer_id in (a_offer, b_offer):
        r = owner.put(f"/owner/projects/{pid}/offers/{offer_id}/shortlist")
        assert r.status_code == 200, r.text
        assert (r.json()["shortlisted"], r.json()["offer_revision"], r.json()["material_revision"], r.json()["added_by_name"]) == (True, 1, 0, "N")
    # The inbox, the offer page and the comparison say so; the third isn't.
    listed = {o["id"]: o["shortlisted"] for o in owner.get(f"/owner/projects/{pid}/offers").json()}
    assert listed == {a_offer: True, b_offer: True, _offer_id(db, pid, c): False}
    assert owner.get(f"/owner/projects/{pid}/offers/{a_offer}").json()["offer"]["shortlisted"] is True
    compared = owner.get(f"/owner/projects/{pid}/offers/compare", params=[("ids", a_offer), ("ids", b_offer)]).json()["offers"]
    assert [o["shortlisted"] for o in compared] == [True, True]
    # Not an award: the requirement, the offers and their statuses are as they were; nobody was told.
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.closed
    assert {o.id: (o.status, o.amount, o.message, o.revision, o.updated_at) for o in db.query(Offer)} == before
    assert db.query(Notification).count() == notes_before
    # Providers never see it -- their own offer included.
    for sp in (a, b, c):
        mine = sp.get(f"/projects/{pid}/offers/mine").json()
        assert mine.get("shortlisted") is None
        assert sp.get(f"/owner/projects/{pid}/offers/{a_offer}/shortlist").status_code == 403
        assert sp.put(f"/owner/projects/{pid}/offers/{a_offer}/shortlist").status_code == 403
        assert "shortlist" not in sp.get(f"/projects/{pid}").text.lower() and "shortlist" not in sp.get("/service-provider/my-bids").text.lower()
    # Off the shortlist again; recorded both ways.
    assert owner.delete(f"/owner/projects/{pid}/offers/{b_offer}/shortlist").json()["shortlisted"] is False
    assert {x.action for x in db.query(AuditLog).filter(AuditLog.target_id == b_offer)} >= {"offer.shortlisted", "offer.unshortlisted"}


def test_retries_two_tabs_and_colleagues_converge(db):
    fahad, noura, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _closed(db, fahad, a)
    offer_id = _offer_id(db, pid, a)
    url = f"/owner/projects/{pid}/offers/{offer_id}/shortlist"
    # Double click, a second tab, a colleague: one shortlisting.
    for client in (fahad, fahad, noura):
        assert client.put(url).json()["shortlisted"] is True
    assert db.query(OfferShortlist).count() == 1
    assert db.query(AuditLog).filter(AuditLog.target_id == offer_id, AuditLog.action == "offer.shortlisted").count() == 1
    # A stale tab removing, then another re-adding: the last request wins, cleanly.
    assert noura.delete(url).json()["shortlisted"] is False
    assert fahad.delete(url).json()["shortlisted"] is False
    assert db.query(OfferShortlist).count() == 0
    assert noura.get(url).json()["shortlisted"] is False


def test_only_live_offers_on_ones_own_requirement_during_evaluation(db):
    owner = _account(db, "owner", "owner@example.com")
    stranger = _account(db, "owner", "stranger@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    # Open: offers may still change, so nothing to shortlist yet.
    open_pid = _tender(owner, "Open")
    _submitted(a, open_pid)
    assert owner.put(f"/owner/projects/{open_pid}/offers/{_offer_id(db, open_pid, a)}/shortlist").status_code == 400
    # A withdrawn offer (withdrawn while open) can't become a preferred one once closed.
    wd = _tender(owner, "Withdrawn")
    _submitted(a, wd)
    _submitted(b, wd)
    assert b.post(f"/projects/{wd}/offers/withdraw").status_code == 200
    assert owner.post(f"/owner/projects/{wd}/close").status_code == 200
    assert owner.put(f"/owner/projects/{wd}/offers/{_offer_id(db, wd, b)}/shortlist").status_code == 404
    # Another requirement's offer under this requirement, another owner: refused.
    pid = _closed(db, owner, a, title="Mine")
    other = _closed(db, stranger, b, title="Theirs")
    assert owner.put(f"/owner/projects/{pid}/offers/{_offer_id(db, other, b)}/shortlist").status_code == 404
    assert stranger.put(f"/owner/projects/{pid}/offers/{_offer_id(db, pid, a)}/shortlist").status_code == 404
    assert db.query(OfferShortlist).count() == 0
    # Sealed until the deadline: nothing to tell apart.
    sealed = _tender(owner, "Sealed", sealed=True)
    _submitted(a, sealed)
    assert owner.put(f"/owner/projects/{sealed}/offers/{_offer_id(db, sealed, a)}/shortlist").status_code == 404
    # Awarded: the shortlist stays as it was and can't change.
    a_offer = _offer_id(db, pid, a)
    assert owner.put(f"/owner/projects/{pid}/offers/{a_offer}/shortlist").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/offers/{a_offer}/approve").status_code == 200
    assert owner.delete(f"/owner/projects/{pid}/offers/{a_offer}/shortlist").status_code == 400
    assert owner.get(f"/owner/projects/{pid}/offers/{a_offer}/shortlist").json()["shortlisted"] is True
    # Ended outside U-Tender: frozen too.
    ended = _closed(db, owner, a, title="Ended")
    e_offer = _offer_id(db, ended, a)
    owner.put(f"/owner/projects/{ended}/offers/{e_offer}/shortlist")
    assert owner.post(f"/owner/projects/{ended}/close-externally", json={}).status_code == 200
    assert owner.put(f"/owner/projects/{ended}/offers/{e_offer}/shortlist").status_code == 400
    assert db.query(OfferShortlist).filter(OfferShortlist.offer_id == e_offer).count() == 1

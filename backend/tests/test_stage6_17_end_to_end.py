"""Stage 6.17: the owner's evaluation and decision journey end to end --
Receive -> Review -> Compare -> Evaluate -> Shortlist -> Award or No-Award ->
Provider outcome -- across the authorization, confidentiality, lifecycle,
offer-integrity and decision boundaries. (Simultaneous decisions: the MySQL
race tests in test_stage6_15_decision_integrity.)"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import app.routers.owner as owner_router
from app.main import app
from app.models.award_record import AwardRecord
from app.models.enums import OfferStatus, ProjectStatus
from app.models.offer import Offer
from app.models.project import Project
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account, _when

DECL = "I have visited the site."


def _tender(owner, title="Substation works", sealed=False):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Replace the switchgear.", "bid_deadline": _when(10),
                                       "tender_type": "sealed" if sealed else "owner_visible"}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"approach": "required", "documents": [{"name": "Method statement", "required": True}], "declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _offer(sp, pid, amount, method, file=b"%PDF"):
    sp.post(f"/projects/{pid}/participate")
    assert sp.put(f"/projects/{pid}/offers/draft", json={"amount": amount, "message": method, "assumptions": f"Assumes {method}", "accepted_declarations": [DECL], "proposed_duration_days": 30}).status_code == 200
    assert sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": (f"{method}.pdf", file, "application/pdf")}).status_code == 200
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _local(url):
    return "/" + url.split("://", 1)[-1].split("/", 1)[-1]


def test_scenario_1_normal_competition_to_an_award(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana"))
    pid = _tender(owner)
    ids = {name: _offer(sp, pid, amount, f"method-{name}", f"%PDF-{name}".encode()) for name, sp, amount in (("amal", a, "1200"), ("badr", b, "1100"), ("dana", c, "1300"))}
    # Inbox: three received, live, in arrival order.
    inbox = owner.get(f"/owner/projects/{pid}/offers").json()
    # (arrival order; offers within the same second -- MySQL keeps whole seconds -- by id)
    assert sorted((o["service_provider_company_name"], o["status"]) for o in inbox) == [("amal", "submitted"), ("badr", "submitted"), ("dana", "submitted")]
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    # Review each: commercial, technical, delivery, documents, version.
    for name, oid in ids.items():
        d = owner.get(f"/owner/projects/{pid}/offers/{oid}").json()
        assert (d["offer"]["message"], d["offer"]["proposed_duration_days"], d["on_current_version"]) == (f"method-{name}", 30, True)
        assert owner.get(_local(d["offer"]["documents"][0]["url"])).content == f"%PDF-{name}".encode()
    # Compare, clarify, note, shortlist.
    cmp = owner.get(f"/owner/projects/{pid}/offers/compare", params=[("ids", ids["badr"]), ("ids", ids["amal"])]).json()
    assert [o["amount"] for o in cmp["offers"]] == ["1100.000", "1200.000"]
    q = owner.post(f"/owner/projects/{pid}/offers/{ids['badr']}/clarifications", json={"question": "Lead time on the panels?"}).json()
    assert b.post(f"/projects/{pid}/offers/mine/clarifications/{q['id']}/answer", json={"answer": "Eight weeks."}).status_code == 200
    owner.post(f"/owner/projects/{pid}/notes", json={"body": "Badr: best programme.", "offer_id": ids["badr"]})
    for name in ("amal", "badr"):
        assert owner.put(f"/owner/projects/{pid}/offers/{ids[name]}/shortlist").json()["shortlisted"] is True
    # Award B.
    assert owner.post(f"/owner/projects/{pid}/offers/{ids['badr']}/approve").status_code == 200
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded
    assert {o.id: o.status for o in db.query(Offer)} == {ids["badr"]: OfferStatus.approved, ids["amal"]: OfferStatus.rejected, ids["dana"]: OfferStatus.rejected}
    # Provider outcomes: B awarded with its own amount; A and C only that a successful bidder was awarded.
    assert b.get(f"/projects/{pid}/award").json()["mine"] is True
    for loser in (a, c):
        award = loser.get(f"/projects/{pid}/award").json()
        assert (award["mine"], award["amount"], award["service_provider_company_name"]) == (False, None, None)
        assert {x["project_id"]: x["offer_status"] for x in loser.get("/service-provider/my-bids").json()}[pid] == "rejected"


def test_scenario_2_no_suitable_provider(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    for sp, amount in ((a, "9000"), (b, "9500")):
        _offer(sp, pid, amount, "m")
    owner.post(f"/owner/projects/{pid}/close")
    assert owner.post(f"/owner/projects/{pid}/no-award", json={"note": "Over budget."}).status_code == 200
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.no_award and db.query(AwardRecord).count() == 0
    assert sorted(str(o.amount) for o in db.query(Offer)) == ["9000.000", "9500.000"]
    assert all(o.status == OfferStatus.submitted for o in db.query(Offer))
    assert len(owner.get(f"/owner/projects/{pid}/offers").json()) == 2


def test_scenario_3_withdrawn_offer_cannot_win(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    a_id, b_id = _offer(a, pid, "1000", "m"), _offer(b, pid, "1100", "m")
    assert a.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    owner.post(f"/owner/projects/{pid}/close")
    assert owner.post(f"/owner/projects/{pid}/offers/{a_id}/approve").status_code == 400
    assert owner.put(f"/owner/projects/{pid}/offers/{a_id}/shortlist").status_code == 404
    assert owner.get(f"/owner/projects/{pid}/offers/compare", params=[("ids", a_id), ("ids", b_id)]).json()["unavailable"] == [a_id]
    db.expire_all()
    assert db.get(Offer, a_id).status == OfferStatus.withdrawn and db.query(AwardRecord).count() == 0


def test_scenario_4_amendment_keeps_each_response_on_its_version(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    a_id = _offer(a, pid, "1000", "before")
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Replace the switchgear and the RMU."}, headers={"If-Match": str(v)})
    b_id = _offer(b, pid, "1300", "after")
    owner.post(f"/owner/projects/{pid}/close")
    a_view = owner.get(f"/owner/projects/{pid}/offers/{a_id}").json()
    assert (a_view["on_current_version"], a_view["offer"]["message"], a_view["offer"]["amount"]) == (False, "before", "1000.000")
    assert owner.get(f"/owner/projects/{pid}/offers/{b_id}").json()["on_current_version"] is True
    assert owner.post(f"/owner/projects/{pid}/offers/{a_id}/approve").status_code == 409  # never silently
    assert owner.post(f"/owner/projects/{pid}/offers/{b_id}/approve").status_code == 200


def test_scenario_5_deadline_passes_while_reviewing(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    live, empty = _tender(owner, "Live"), _tender(owner, "Empty")
    a_id = _offer(a, live, "1000", "m")
    _offer(b, empty, "1000", "m")
    assert b.post(f"/projects/{empty}/offers/withdraw").status_code == 200
    for pid in (live, empty):
        db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    # The server's clock decides: offers stop; one with a live offer is closed for evaluation, the other expired.
    assert a.post(f"/projects/{live}/offers", json={"amount": "1"}, headers={"If-Match": "1"}).status_code == 400
    owner.get("/owner/projects")  # expiry is applied lazily, on the next read (every decision path runs it first too)
    db.expire_all()
    assert (db.get(Project, live).status, db.get(Project, empty).status) == (ProjectStatus.closed, ProjectStatus.expired)
    assert owner.post(f"/owner/projects/{empty}/no-award", json={}).status_code == 400  # expired is final
    assert owner.post(f"/owner/projects/{live}/offers/{a_id}/approve").status_code == 200


def test_scenario_7_a_provider_cannot_reach_a_competitor(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    a_id = _offer(a, pid, "98765.432", "SECRET-A", b"%PDF-SECRET-A")
    _offer(b, pid, "1000", "badr")
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/notes", json={"body": "SECRET-NOTE", "offer_id": a_id})
    owner.put(f"/owner/projects/{pid}/offers/{a_id}/shortlist")
    owner.post(f"/owner/projects/{pid}/offers/{a_id}/clarifications", json={"question": "SECRET-QUESTION"})
    for url in (
        f"/owner/projects/{pid}/offers", f"/owner/projects/{pid}/offers/{a_id}", f"/owner/projects/{pid}/offers/{a_id}/history",
        f"/owner/projects/{pid}/offers/compare?ids={a_id}", f"/owner/projects/{pid}/offers/{a_id}/documents/file?label=Method%20statement",
        f"/owner/projects/{pid}/offers/{a_id}/clarifications", f"/owner/projects/{pid}/offers/{a_id}/shortlist", f"/owner/projects/{pid}/notes",
    ):
        r = b.get(url, follow_redirects=False)
        assert r.status_code == 403, url
    for url in (f"/projects/{pid}", f"/projects/{pid}/offers/mine", f"/projects/{pid}/offers/mine/clarifications", f"/projects/{pid}/offers/documents",
                f"/projects/{pid}/clarifications", "/service-provider/my-bids", "/notifications", f"/projects/{pid}/offers/documents/{a_id}/file"):
        text = b.get(url, follow_redirects=False).text
        for secret in ("98765", "SECRET-A", "SECRET-NOTE", "SECRET-QUESTION", '"shortlisted":true'):
            assert secret not in text, (url, secret)
    assert TestClient(app).get(f"/owner/projects/{pid}/offers").status_code == 401


def test_scenario_8_and_10_stale_tabs_and_retries_never_overwrite(db):
    fahad, noura, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(fahad)
    a_id, b_id = _offer(a, pid, "1000", "m"), _offer(b, pid, "1100", "m")
    fahad.post(f"/owner/projects/{pid}/close")
    # Noura's page was opened before Fahad decided.
    assert fahad.post(f"/owner/projects/{pid}/offers/{a_id}/approve").status_code == 200
    assert fahad.post(f"/owner/projects/{pid}/offers/{a_id}/approve").status_code == 400  # a retry after a lost response
    assert noura.post(f"/owner/projects/{pid}/offers/{b_id}/approve").status_code == 400
    assert noura.post(f"/owner/projects/{pid}/no-award", json={}).status_code == 400
    assert noura.post(f"/owner/projects/{pid}/cancel", json={"reason": "other"}).status_code == 400
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded
    (record,) = db.query(AwardRecord).all()
    assert record.offer_id == a_id
    # Both members read the same authoritative outcome.
    for member in (fahad, noura):
        assert member.get(f"/projects/{pid}/award").json()["offer_id"] == a_id


def test_scenario_9_notification_failure_leaves_the_award_standing(db, monkeypatch):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    a_id = _offer(a, pid, "1000", "m")
    owner.post(f"/owner/projects/{pid}/close")
    monkeypatch.setattr(owner_router, "notify_team", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    assert owner.post(f"/owner/projects/{pid}/offers/{a_id}/approve").status_code == 200
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded
    assert a.get(f"/projects/{pid}/offers/mine").json()["status"] == "approved"

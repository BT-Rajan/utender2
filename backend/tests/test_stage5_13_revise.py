"""Stage 5.13: revising a submitted offer before the deadline -- the existing
rule (revise or withdraw until offers close, every revision recorded) made
safe: one current offer, the previous version kept in full (what it said,
its documents, when and by whom), never from a stale page, never after the
deadline or outside the open lifecycle, and never touching the current
submission when it fails."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import OfferStatus
from app.models.offer import Offer, OfferRevision
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _when

needs_mysql = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs real row locking (MySQL)")
DECL = "I have visited the site."


def _d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _get(client, url):
    return client.get("/" + url.split("://", 1)[-1].split("/", 1)[-1])


def _tender(owner, title="HV works", sealed=False):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Substation.", "bid_deadline": _when(10),
                                       "tender_type": "sealed" if sealed else "owner_visible"}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"approach": "required", "documents": [{"name": "Method statement", "required": True}], "declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _submitted(sp, pid):
    sp.post(f"/projects/{pid}/participate")
    sp.put(f"/projects/{pid}/offers/draft", json={"amount": "1000", "message": "Method v1", "assumptions": "A1", "accepted_declarations": [DECL],
                                                  "proposed_start_date": _d(20), "proposed_duration_days": 30})
    sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("method-v1.pdf", b"%PDF-v1", "application/pdf")})
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code == 200, r.text
    return r.json()


REV2 = {"amount": "900", "message": "Method v2", "assumptions": "A2", "accepted_declarations": [DECL], "proposed_start_date": None, "proposed_duration_days": 25}


def test_revise_keeps_one_current_offer_and_the_previous_version_in_full(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    v1 = _submitted(sp, pid)
    me = sp.get("/auth/me").json()["id"]
    # A replacement document while preparing the revision: the owner still has the submitted one.
    sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("method-v2.pdf", b"%PDF-v2", "application/pdf")})
    seen = owner.get(f"/owner/projects/{pid}/offers").json()[0]
    assert [d["file_name"] for d in seen["documents"]] == ["method-v1.pdf"] and _get(owner, seen["documents"][0]["url"]).content == b"%PDF-v1"
    # Revise -> resubmit: the same offer, revision 2, everything as revised (timing included).
    r = sp.post(f"/projects/{pid}/offers", json={**REV2, "proposed_start_date": _d(21)}, headers={"If-Match": "1"})
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert (v2["id"], v2["status"], v2["revision"], Decimal(v2["amount"]), v2["message"], v2["proposed_start_date"], v2["proposed_duration_days"]) == (
        v1["id"], "submitted", 2, Decimal("900"), "Method v2", _d(21), 25)
    assert v2["submitted_at"] == v1["submitted_at"]  # first submitted then; revised now
    # 4. One current offer.
    assert db.query(Offer).count() == 1 and [o["id"] for o in owner.get(f"/owner/projects/{pid}/offers").json()] == [v1["id"]]
    now_seen = owner.get(f"/owner/projects/{pid}/offers").json()[0]
    assert (now_seen["amount"], now_seen["message"], [d["file_name"] for d in now_seen["documents"]]) == ("900.000", "Method v2", ["method-v2.pdf"])
    # 3. The previous version, in full, as submitted -- for the provider and the owner; no storage paths.
    for client, url in ((sp, f"/projects/{pid}/offers/mine/history"), (owner, f"/owner/projects/{pid}/offers/{v1['id']}/history")):
        history = client.get(url).json()
        assert len(history) == 1, url
        h = history[0]
        assert (h["revision_number"], h["amount"], h["message"], h["assumptions"], h["declarations_accepted"], h["proposed_duration_days"], h["submitted_by"]) == (
            1, "1000.000", "Method v1", "A1", [DECL], 30, me)
        doc = h["documents"][0]
        assert (len(h["documents"]), doc["label"], doc["file_name"], "file_path" in doc) == (1, "Method statement", "method-v1.pdf", False) and h["submitted_at"]
        assert _get(client, doc["url"]).content == b"%PDF-v1"  # the earlier version's file, by a short-lived link
    # The file that went with version 1 is kept, not deleted by the replacement.
    v1_path = db.query(OfferRevision).one().documents[0]["file_path"]
    from app.services.storage import get_storage
    assert get_storage().download("offer-documents", v1_path) == b"%PDF-v1"


def test_stale_tabs_colleagues_and_repeats_never_overwrite_a_newer_revision(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    pid = _tender(owner)
    _submitted(boss, pid)
    # Both colleagues opened revision 1; the first revision lands, the second is refused.
    assert boss.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}).status_code == 200
    r = eng.post(f"/projects/{pid}/offers", json={**REV2, "amount": "800"}, headers={"If-Match": "1"})
    assert r.status_code == 409 and "changed somewhere else" in r.json()["detail"]
    # A retried request with the same (now stale) revision: refused, no second revision.
    assert boss.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}).status_code == 409
    offer = db.query(Offer).one()
    db.refresh(offer)
    assert (offer.revision, offer.amount, db.query(OfferRevision).count()) == (2, Decimal("900"), 1)
    # Reloaded, the colleague revises the latest.
    assert eng.post(f"/projects/{pid}/offers", json={**REV2, "amount": "800"}, headers={"If-Match": "2"}).json()["revision"] == 3


def test_deadline_lifecycle_and_amendment(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    pids = {s: _tender(owner, s) for s in ("near", "at", "after", "closed_early", "canceled", "suspended", "paused", "amended")}
    for pid in pids.values():
        _submitted(sp, pid)
    near_deadline = (datetime.utcnow() + timedelta(seconds=30)).replace(microsecond=0)  # whole seconds, as stored
    db.get(Project, pids["near"]).bid_deadline = near_deadline
    db.get(Project, pids["at"]).bid_deadline = datetime.utcnow().replace(microsecond=0)  # whole seconds, as MySQL stores it
    db.get(Project, pids["after"]).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner.post(f"/owner/projects/{pids['closed_early']}/close")
    owner.post(f"/owner/projects/{pids['canceled']}/cancel", json={"reason": "not_needed"})
    admin.post(f"/admin/projects/{pids['suspended']}/suspend", json={"suspended": True})
    owner.post(f"/owner/projects/{pids['paused']}/pause", json={"reason": "Permit."})
    # 2. Close to the deadline: allowed; at it or after it (server clock), and outside the open lifecycle: refused.
    assert sp.post(f"/projects/{pids['near']}/offers", json=REV2, headers={"If-Match": "1"}).status_code == 200
    for state in ("at", "after", "closed_early", "canceled", "suspended", "paused"):
        r = sp.post(f"/projects/{pids[state]}/offers", json=REV2, headers={"If-Match": "1"})
        assert r.status_code == 400, (state, r.json())
        # 10. The submitted offer is untouched.
        o = db.query(Offer).filter(Offer.project_id == pids[state]).one()
        db.refresh(o)
        assert (o.revision, o.amount, o.message) == (1, Decimal("1000"), "Method v1"), state
    # A revision never moves the deadline.
    db.expire_all()
    assert db.get(Project, pids["near"]).bid_deadline == near_deadline
    # 6. A material amendment: the submitted offer keeps its version; revising makes the new version against the
    # current requirement, and the old one stays on record against the old one.
    pid = pids["amended"]
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Substation plus a second bay."}, headers={"If-Match": str(v)})
    assert sp.get(f"/projects/{pid}/offers/mine").json()["based_on_material_revision"] == 0
    assert sp.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}).json()["based_on_material_revision"] == 1
    assert [h["based_on_material_revision"] for h in sp.get(f"/projects/{pid}/offers/mine/history").json()] == [0]


def test_failed_revision_and_other_providers(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com")
    pid = _tender(owner, sealed=True)
    v1 = _submitted(sp, pid)
    rival_offer = _submitted(rival, pid)
    # 10. Incomplete / invalid revisions: refused, the current submission exactly as it was, no history entry.
    for bad in ({**REV2, "message": ""}, {**REV2, "amount": "-1"}, {**REV2, "accepted_declarations": []},
                {**REV2, "proposed_start_date": _d(1)}, {**REV2, "proposed_completion_date": _d(40), "proposed_duration_days": 10}):
        assert sp.post(f"/projects/{pid}/offers", json=bad, headers={"If-Match": "1"}).status_code in (400, 422), bad
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["revision"], mine["amount"], mine["message"], mine["proposed_duration_days"]) == (1, "1000.000", "Method v1", 30)
    assert db.query(OfferRevision).count() == 0
    # 9. Another provider "revising" with this offer's ids revises only their own.
    r = rival.post(f"/projects/{pid}/offers", json={**REV2, "offer_id": v1["id"], "service_provider_id": v1["service_provider_id"]}, headers={"If-Match": "1"})
    assert r.status_code == 200 and r.json()["id"] == rival_offer["id"]
    assert sp.get(f"/projects/{pid}/offers/mine").json()["message"] == "Method v1"
    # 5. Revising shows nothing of the competitor; sealed: the owner still sees no content.
    assert "Method v2" not in sp.get(f"/projects/{pid}/offers/mine/history").text
    assert all(o["amount"] is None and o["message"] is None for o in owner.get(f"/owner/projects/{pid}/offers").json())
    assert rival.get(f"/projects/{pid}/offers/mine/history").json()[0]["message"] == "Method v1"  # their own v1
    # Withdraw and resubmit: the same offer, recorded.
    assert sp.post(f"/projects/{pid}/offers/withdraw").json()["status"] == "withdrawn"
    again = sp.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "2"}).json()
    assert (again["id"], again["status"], again["revision"]) == (v1["id"], "submitted", 3)
    assert [h["status"] for h in sp.get(f"/projects/{pid}/offers/mine/history").json()] == ["submitted", "withdrawn"]


@needs_mysql
def test_simultaneous_revisions_one_wins(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    clients = [sp]
    for _ in range(3):
        c = TestClient(app)
        c.post("/auth/login", json={"email": "noor@example.com", "password": "password123"})
        clients.append(c)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: c.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}), clients))
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409]
    db.expire_all()
    assert db.query(Offer).one().revision == 2 and db.query(OfferRevision).count() == 1

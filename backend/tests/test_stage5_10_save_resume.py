"""Stage 5.10: save and resume an offer -- the whole form saved on the one
draft in a single step (all or nothing), found again after leaving, logging
out or opening the requirement again, shown as in progress, re-judged
against the requirement as it is now, and never overwritten by a stale page
or turned into an offer by saving."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import OfferStatus
from app.models.offer import Offer
from app.models.participation import Participation
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _publish, _when

SAVE = "/projects/{}/offers/draft"
DECL = "I have visited the site."


def _d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _login(email):
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _with_rules(owner, title="Rewiring"):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Rewire.", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"approach": "required", "declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


FORM = {"amount": "900", "message": "Method.", "assumptions": "Excludes dewatering.", "accepted_declarations": [DECL],
        "proposed_start_date": None, "proposed_duration_days": 20, "timeline_estimate": "Three weeks"}


def test_save_leave_logout_return_continue(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _with_rules(owner)
    draft = sp.post(f"/projects/{pid}/participate").json()["offer_id"]
    # Partial information, saved in one step; nothing submitted.
    r = sp.put(SAVE.format(pid), json={"amount": "900", "message": "Method."}, headers={"If-Match": "0"})
    assert r.status_code == 200 and r.json()["status"] == "draft" and r.json()["draft_version"] == 1
    assert r.json()["updated_at"].endswith("Z")  # an explicit UTC instant
    # Refresh: still there.
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["id"], Decimal(mine["amount"]), mine["message"]) == (draft, Decimal("900"), "Method.")
    # Log out, log in, open the requirement again (and again): the same draft, shown as in progress.
    sp.post("/auth/logout")
    back = _login("noor@example.com")
    for _ in range(3):
        verdict = back.get(f"/projects/{pid}").json()["participation"]
        assert (verdict["started"], verdict["offer_id"], verdict["offer_status"]) == (True, draft, "draft")
        back.post(f"/projects/{pid}/participate")
    assert db.query(Offer).count() == 1 and db.query(Participation).count() == 1
    assert next(p for p in back.get("/service-provider/feed").json()["items"] if p["id"] == pid)["my_offer_status"] == "draft"
    preparing = back.get("/service-provider/preparing").json()
    assert preparing[0]["offer_id"] == draft and preparing[0]["last_saved_at"]
    # Continue from the saved state; the rest of the form saved too.
    r = back.put(SAVE.format(pid), json=FORM, headers={"If-Match": "1"}).json()
    assert (r["assumptions"], r["declarations_accepted"], r["proposed_duration_days"], r["timeline_estimate"], r["draft_version"]) == (
        "Excludes dewatering.", [DECL], 20, "Three weeks", 2)
    assert back.get(f"/projects/{pid}/offers/draft/check").json()["ready"] is True
    # Saving never made it an offer: not the owner's, not a competitor's, not a bid.
    assert owner.get(f"/owner/projects/{pid}/offers").json() == [] and back.get("/service-provider/my-bids").json() == []
    assert db.get(Project, pid).tender_type_locked is False


def test_a_failed_save_leaves_the_saved_draft_untouched(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _with_rules(owner)
    sp.post(f"/projects/{pid}/participate")
    sp.put(SAVE.format(pid), json=FORM)
    before = sp.get(f"/projects/{pid}/offers/mine").json()
    # One bad part (timing before offers close; a declaration not on the requirement; a bad price):
    # nothing of the save is written, the version doesn't move -- a retry isn't a false conflict.
    for bad in ({**FORM, "amount": "1000", "proposed_start_date": _d(1)},
                {**FORM, "message": "Changed", "accepted_declarations": ["Something else"]},
                {**FORM, "assumptions": "Changed", "amount": "-1"}):
        assert sp.put(SAVE.format(pid), json=bad, headers={"If-Match": str(before["draft_version"])}).status_code in (400, 422)
    after = sp.get(f"/projects/{pid}/offers/mine").json()
    assert {k: after[k] for k in ("amount", "message", "assumptions", "proposed_start_date", "draft_version")} == {
        k: before[k] for k in ("amount", "message", "assumptions", "proposed_start_date", "draft_version")}
    # The corrected retry goes through on the same version.
    assert sp.put(SAVE.format(pid), json={**FORM, "amount": "1000"}, headers={"If-Match": str(before["draft_version"])}).status_code == 200


def test_two_tabs_or_two_colleagues_never_overwrite_newer_work(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    pid = _with_rules(owner)
    boss.post(f"/projects/{pid}/participate")
    eng.post(f"/projects/{pid}/participate")  # the organization's same draft, not a second
    assert db.query(Offer).count() == 1
    # Both open version 0; the first save lands, the second is refused, not merged or overwritten.
    assert boss.put(SAVE.format(pid), json={**FORM, "amount": "900"}, headers={"If-Match": "0"}).status_code == 200
    r = eng.put(SAVE.format(pid), json={**FORM, "amount": "700"}, headers={"If-Match": "0"})
    assert r.status_code == 409 and "changed somewhere else" in r.json()["detail"]
    # A repeated request with the same (now stale) version: refused too; the saved draft is the first one.
    assert boss.put(SAVE.format(pid), json={**FORM, "amount": "900"}, headers={"If-Match": "0"}).status_code == 409
    mine = eng.get(f"/projects/{pid}/offers/mine").json()
    assert (Decimal(mine["amount"]), mine["draft_version"]) == (Decimal("900"), 1)
    # Reloaded, the colleague continues from the latest.
    assert eng.put(SAVE.format(pid), json={**FORM, "amount": "700"}, headers={"If-Match": "1"}).status_code == 200


def test_resume_follows_the_requirement_as_it_is_now(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    extended, amended, suspended, expired, canceled = (_with_rules(owner, t) for t in ("Extended", "Amended", "Suspended", "Expired", "Canceled"))
    for pid in (extended, amended, suspended, expired, canceled):
        sp.post(f"/projects/{pid}/participate")
        assert sp.put(SAVE.format(pid), json=FORM).status_code == 200
    # Extended: the current deadline is what the provider sees; saving never moves it.
    later = _when(20)
    v = owner.get(f"/projects/{extended}").json()["version"]
    owner.patch(f"/projects/{extended}", json={"bid_deadline": later}, headers={"If-Match": str(v)})
    deadline = sp.get(f"/projects/{extended}").json()["bid_deadline"]
    assert deadline == later
    sp.put(SAVE.format(extended), json=FORM)
    assert sp.get(f"/projects/{extended}").json()["bid_deadline"] == deadline
    # Amended: flagged; no save, no "ready", no submission against the old version until reviewed.
    v = owner.get(f"/projects/{amended}").json()["version"]
    owner.patch(f"/projects/{amended}", json={"description": "Rewire, plus 6 outdoor points."}, headers={"If-Match": str(v)})
    seen = sp.get(f"/projects/{amended}").json()
    assert seen["description"] == "Rewire, plus 6 outdoor points." and seen["participation"]["seen_material_revision"] == 0
    assert sp.put(SAVE.format(amended), json=FORM).status_code == 409
    assert sp.get(f"/projects/{amended}/offers/draft/check").json()["ready"] is False
    assert sp.post(f"/projects/{amended}/offers", json={"amount": "900", "message": "m", "accepted_declarations": [DECL]}).status_code == 409
    assert db.query(Offer).filter(Offer.project_id == amended).one().based_on_material_revision == 0
    # Suspended, past the deadline, cancelled: kept as saved, but no saving, no submitting.
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})
    db.get(Project, expired).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.post(f"/owner/projects/{canceled}/cancel", json={"reason": "not_needed"})
    for pid in (suspended, expired, canceled):
        assert sp.put(SAVE.format(pid), json=FORM).status_code == 400, pid
        assert sp.post(f"/projects/{pid}/offers", json={"amount": "900", "message": "m", "accepted_declarations": [DECL]}).status_code == 400
        assert sp.get(f"/projects/{pid}/offers/draft/check").json()["ready"] is False
        assert sp.get(f"/projects/{pid}/offers/mine").json()["message"] == "Method."
    assert all(o.status == OfferStatus.draft for o in db.query(Offer))
    assert {p["project_id"] for p in sp.get("/service-provider/preparing").json()} == {extended, amended}

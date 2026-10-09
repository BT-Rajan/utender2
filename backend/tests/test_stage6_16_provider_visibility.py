"""Stage 6.16: provider notification & decision visibility. After the owner's
final decision each bidder sees the authoritative outcome of their own offer
-- awarded, not selected, withdrawn, or the requirement's ending -- through
the existing statuses and notifications; never another bidder's price or
anything of the owner's evaluation; a notification failure never undoes or
fails the decision."""
import app.routers.owner as owner_router
from app.models.enums import NotificationType, ProjectStatus
from app.models.notification import Notification
from app.models.project import Project
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender

SECRET_NOTE = "Internal: Badr too expensive, Amal preferred."


def _offer_id(sp, pid):
    return sp.get(f"/projects/{pid}/offers/mine").json()["id"]


def _mine_notes(db, sp):
    uid = sp.get("/auth/me").json()["id"]
    return {n.type: n for n in db.query(Notification).filter(Notification.user_id == uid)}


def test_award_outcome_for_the_winner_the_others_and_nobody_else(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b, c, outsider = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana", "eid"))
    pid = _tender(owner)
    for sp in (a, b, c):
        _submitted(sp, pid)
    r = b.post(f"/projects/{pid}/offers", json={"amount": "777.555", "message": "Badr v2", "accepted_declarations": ["I have visited the site."], "proposed_duration_days": 20}, headers={"If-Match": "1"})
    assert r.status_code == 200, r.text
    assert c.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    owner.post(f"/owner/projects/{pid}/close")
    a_offer = _offer_id(a, pid)
    owner.put(f"/owner/projects/{pid}/offers/{a_offer}/shortlist")
    owner.post(f"/owner/projects/{pid}/notes", json={"body": SECRET_NOTE, "offer_id": a_offer})
    assert owner.post(f"/owner/projects/{pid}/offers/{a_offer}/approve").status_code == 200

    # The winner: their offer awarded, and at what.
    award = a.get(f"/projects/{pid}/award").json()
    assert (award["mine"], award["amount"], award["offer_id"]) == (True, "1000.000", a_offer)
    assert a.get(f"/projects/{pid}/offers/mine").json()["status"] == "approved"
    assert {x["project_id"]: x["offer_status"] for x in a.get("/service-provider/my-bids").json()}[pid] == "approved"
    assert NotificationType.award_won in _mine_notes(db, a)
    # Another bidder: not selected, and who won -- never the winning price or offer.
    award = b.get(f"/projects/{pid}/award").json()
    assert (award["mine"], award["amount"], award["offer_id"], award["service_provider_id"], award["service_provider_company_name"]) == (False, None, None, None, None)
    bid = {x["project_id"]: x for x in b.get("/service-provider/my-bids").json()}[pid]
    assert (bid["offer_status"], bid["project_status"], bid["amount"]) == ("rejected", "awarded", "777.555")  # their own price, not the winner's
    assert NotificationType.award_lost in _mine_notes(db, b)
    # Withdrawn before the decision: still withdrawn, and not told they lost.
    assert c.get(f"/projects/{pid}/offers/mine").json()["status"] == "withdrawn"
    assert NotificationType.award_lost not in _mine_notes(db, c) and NotificationType.award_won not in _mine_notes(db, c)
    # Never a bidder: nothing.
    assert outsider.get(f"/projects/{pid}/award").status_code == 404
    # Nothing of the winner's offer, the shortlist or the owner's notes reaches the others -- anywhere they look.
    for sp in (b, c, outsider):
        seen = " ".join(sp.get(u).text for u in (f"/projects/{pid}", f"/projects/{pid}/award", f"/projects/{pid}/offers/mine", "/service-provider/my-bids", "/notifications"))
        assert "1000.000" not in seen and "Method v1" not in seen.replace("Badr v2", "") or sp is c  # c's own withdrawn offer said Method v1
        leaks = [u for u in (f"/projects/{pid}", f"/projects/{pid}/award", f"/projects/{pid}/offers/mine", "/service-provider/my-bids", "/notifications") if SECRET_NOTE in sp.get(u).text]
        assert leaks == [], leaks
        assert '"shortlisted":true' not in seen
    # Batch C: notifications are no longer merged into one overwritten row, so the owner keeps
    # "amal submitted an offer" (its own bidder's name, rightly the owner's to see); the check is on what bidders get.
    owner_id = owner.get("/auth/me").json()["id"]
    owner_notes = [n for n in db.query(Notification) if n.user_id == owner_id]
    assert owner_notes and all("1000" not in n.body and "777" not in n.body for n in owner_notes)  # Batch C:
    for n in db.query(Notification).filter(Notification.user_id != owner_id):  # Batch C:
        assert "1000" not in n.body and "777" not in n.body and "amal" not in n.body.lower() or n.type == NotificationType.award_won


def test_ending_without_award_reads_as_the_requirements_outcome(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    owner.post(f"/owner/projects/{pid}/close")
    assert owner.post(f"/owner/projects/{pid}/no-award", json={"note": SECRET_NOTE}).status_code == 200
    for sp in (a, b):
        detail = sp.get(f"/projects/{pid}").json()
        assert (detail["status"], detail["closure_reason"], detail.get("closure_note")) == ("no_award", "no_suitable_offer", None)
        bid = {x["project_id"]: x for x in sp.get("/service-provider/my-bids").json()}[pid]
        assert (bid["offer_status"], bid["project_status"], bid["closure_reason"]) == ("closed", "no_award", "no_suitable_offer")  # Batch B: live offers are closed on no-award
        assert sp.get(f"/projects/{pid}/award").status_code == 404  # nobody won
        assert sp.get(f"/projects/{pid}/offers/mine").json()["amount"] == "1000.000"  # their offer kept as submitted
        assert NotificationType.tender_no_award in _mine_notes(db, sp)
        assert SECRET_NOTE not in " ".join(sp.get(u).text for u in (f"/projects/{pid}", "/service-provider/my-bids", "/notifications"))


def test_a_failed_notification_never_fails_or_undoes_the_decision(db, monkeypatch):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pids = [_tender(owner, f"R{i}") for i in range(2)]
    for pid in pids:
        _submitted(a, pid)
        _submitted(b, pid)
        owner.post(f"/owner/projects/{pid}/close")

    def broken(*args, **kwargs):
        raise RuntimeError("notification service down")

    monkeypatch.setattr(owner_router, "notify_team", broken)
    assert owner.post(f"/owner/projects/{pids[0]}/offers/{_offer_id(a, pids[0])}/approve").status_code == 200
    assert owner.post(f"/owner/projects/{pids[1]}/no-award", json={}).status_code == 200
    db.expire_all()
    assert [db.get(Project, p).status for p in pids] == [ProjectStatus.awarded, ProjectStatus.no_award]
    # The providers read the outcome from the record all the same.
    assert a.get(f"/projects/{pids[0]}/award").json()["mine"] is True
    assert {x["project_id"]: x["offer_status"] for x in b.get("/service-provider/my-bids").json()}[pids[0]] == "rejected"
    assert {x["project_id"]: x["project_status"] for x in b.get("/service-provider/my-bids").json()}[pids[1]] == "no_award"

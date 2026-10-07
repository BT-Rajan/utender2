"""Stage 5.5: the provider's start and completion commitment -- in the
requirement's own terms (Stage 3.7): a start date, and a completion date or a
duration -- saved on the offer draft without submitting, beside the price
and technical response; checked to make sense by the server's rules; kept as
entered and flagged where it differs from the owner's expected timing; and
never able to change the requirement's own timing."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.models.enums import OfferStatus
from app.models.offer import Offer, OfferRevision
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _publish, _when

TIMING = "/projects/{}/offers/draft/timing"


def _d(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _timed(owner, title="Rewiring with timing", completion=True):
    data = {"title": title, "address": "Kaifan", "description": "Rewire a villa.", "bid_deadline": _when(10), "status": "open", "expected_start_date": _d(20)}
    data |= {"expected_completion_date": _d(50)} if completion else {"expected_duration_days": "30"}
    r = owner.post("/projects", data=data)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_commitment_saved_beside_price_and_method_and_edited_later(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _timed(owner)
    draft = sp.post(f"/projects/{pid}/participate").json()["offer_id"]
    sp.put(f"/projects/{pid}/offers/draft/commercial", json={"amount": "900"})
    sp.put(f"/projects/{pid}/offers/draft/technical", json={"message": "Method."})
    r = sp.put(TIMING.format(pid), json={"proposed_start_date": _d(20), "proposed_completion_date": _d(45), "timeline_estimate": "Six weeks on site"}, headers={"If-Match": "2"})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert (saved["id"], saved["status"], saved["proposed_start_date"], saved["proposed_completion_date"], saved["proposed_duration_days"]) == (draft, "draft", _d(20), _d(45), None)
    assert (Decimal(saved["amount"]), saved["message"], saved["timeline_estimate"], saved["timing_conflicts"]) == (Decimal("900"), "Method.", "Six weeks on site", [])
    assert owner.get(f"/owner/projects/{pid}/offers").json() == []
    # Leave and return: the same commitment on the same draft.
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert (mine["id"], mine["proposed_start_date"], mine["proposed_completion_date"], mine["status"]) == (draft, _d(20), _d(45), "draft")
    # Edit to a duration instead; price and method stay.
    r = sp.put(TIMING.format(pid), json={"proposed_start_date": _d(21), "proposed_duration_days": 25}).json()
    assert (r["proposed_completion_date"], r["proposed_duration_days"], Decimal(r["amount"]), r["message"]) == (None, 25, Decimal("900"), "Method.")
    # Clearing it is allowed while a draft.
    assert sp.put(TIMING.format(pid), json={}).json()["proposed_start_date"] is None


def test_invalid_commitments_are_refused_and_conflicts_flagged_not_changed(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid, by_duration = _timed(owner), _timed(owner, "Duration based", completion=False)
    sp.post(f"/projects/{pid}/participate")
    sp.post(f"/projects/{by_duration}/participate")
    bad = [
        ({"proposed_start_date": "2026-02-30"}, 422),
        ({"proposed_start_date": "next week"}, 422),
        ({"proposed_duration_days": "ten"}, 422),
        ({"proposed_duration_days": 0}, 400),
        ({"proposed_duration_days": 3651}, 400),
        ({"proposed_completion_date": _d(40), "proposed_duration_days": 10}, 400),  # both
        ({"proposed_start_date": _d(40), "proposed_completion_date": _d(30)}, 400),  # out of order
        ({"proposed_start_date": _d(2)}, 400),  # before offers close
        ({"proposed_completion_date": _d(5)}, 400),
        ({"timeline_estimate": "x" * 256}, 422),
    ]
    for payload, code in bad:
        assert sp.put(TIMING.format(pid), json=payload).status_code == code, payload
    # Later than the owner expects: kept exactly as entered, and flagged.
    r = sp.put(TIMING.format(pid), json={"proposed_start_date": _d(25), "proposed_completion_date": _d(60)}).json()
    assert (r["proposed_start_date"], r["proposed_completion_date"], r["timing_conflicts"]) == (_d(25), _d(60), ["starts_later", "finishes_later"])
    # Against an expected duration (30 days): a longer one, or start + duration past the owner's expected finish.
    r = sp.put(TIMING.format(by_duration), json={"proposed_start_date": _d(20), "proposed_duration_days": 40}).json()
    assert r["proposed_duration_days"] == 40 and r["timing_conflicts"] == ["finishes_later", "takes_longer"]
    assert sp.put(TIMING.format(by_duration), json={"proposed_duration_days": 30}).json()["timing_conflicts"] == []
    assert db.query(OfferRevision).count() == 0 and all(o.status == OfferStatus.draft for o in db.query(Offer))


def test_the_owners_timing_is_never_changed_and_others_are_kept_out(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com", organization="Rival Co")
    pid, other = _timed(owner), _timed(owner, "Other")
    sp.post(f"/projects/{pid}/participate")
    before = owner.get(f"/projects/{pid}").json()
    sp.put(TIMING.format(pid), json={"proposed_start_date": _d(22), "expected_start_date": _d(11), "expected_duration_days": 1, "bid_deadline": _when(1)})
    after = owner.get(f"/projects/{pid}").json()
    for field in ("expected_start_date", "expected_completion_date", "expected_duration_days", "bid_deadline", "version"):
        assert after[field] == before[field], field
    # Another provider, with the draft's ids; or a requirement without this provider's draft.
    offer = db.query(Offer).one()
    assert rival.put(TIMING.format(pid), json={"proposed_start_date": _d(30), "offer_id": offer.id, "service_provider_id": offer.service_provider_id}).status_code == 404
    assert sp.put(TIMING.format(other), json={"proposed_start_date": _d(30)}).status_code == 404
    # A stale tab is refused.
    v = sp.get(f"/projects/{pid}/offers/mine").json()["draft_version"]
    assert sp.put(TIMING.format(pid), json={"proposed_start_date": _d(23)}, headers={"If-Match": str(v - 1)}).status_code == 409
    db.expire_all()
    assert db.query(Offer).one().proposed_start_date == date.today() + timedelta(days=22)


def test_timing_amendment_closure_and_the_submission_trail(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    pid, suspended, expiring = _timed(owner), _timed(owner, "Suspended"), _timed(owner, "Expiring")
    for p in (pid, suspended, expiring):
        sp.post(f"/projects/{p}/participate")
        assert sp.put(TIMING.format(p), json={"proposed_start_date": _d(20), "proposed_completion_date": _d(45)}).status_code == 200
    # The owner moves the expected completion earlier (a material change): no commitment is saved
    # against the old timing until the current one has been reviewed -- then it is judged against it.
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"expected_completion_date": _d(40)}, headers={"If-Match": str(v)}).status_code == 200
    assert sp.put(TIMING.format(pid), json={"proposed_start_date": _d(20), "proposed_completion_date": _d(45)}).status_code == 409
    sp.post(f"/projects/{pid}/participate")
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert mine["based_on_material_revision"] == 1 and mine["timing_conflicts"] == ["finishes_later"]
    # Suspended or past its deadline: kept, not editable.
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})
    db.get(Project, expiring).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    for p in (suspended, expiring):
        assert sp.put(TIMING.format(p), json={"proposed_duration_days": 5}).status_code == 400
    # A required completion period is answered by the committed completion; the owner sees it once submitted,
    # and a later revision keeps the earlier commitment in the offer's history.
    req = owner.post("/projects", data={"title": "Period required", "address": "x", "description": "d", "bid_deadline": _when(10), "expected_start_date": _d(20), "expected_duration_days": "30"}).json()["id"]
    owner.put(f"/projects/{req}/response-requirements", json={"completion_period": "required"})
    owner.post(f"/owner/projects/{req}/publish")
    sp.post(f"/projects/{req}/participate")
    assert sp.post(f"/projects/{req}/offers", json={"amount": "900"}).status_code == 400  # nothing yet
    sp.put(TIMING.format(req), json={"proposed_start_date": _d(20), "proposed_duration_days": 35})
    assert sp.post(f"/projects/{req}/offers", json={"amount": "900"}).status_code == 200
    seen = owner.get(f"/owner/projects/{req}/offers").json()[0]
    assert (seen["proposed_start_date"], seen["proposed_duration_days"], seen["timing_conflicts"]) == (_d(20), 35, ["finishes_later", "takes_longer"])
    sp.post(f"/projects/{req}/offers", json={"amount": "850", "timeline_estimate": "Five weeks"})
    assert [r["proposed_duration_days"] for r in sp.get(f"/projects/{req}/offers/mine/history").json()] == [35]

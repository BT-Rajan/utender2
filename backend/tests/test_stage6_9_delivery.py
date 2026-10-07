"""Stage 6.9: delivery & commitment evaluation. The owner sees each provider's
start / completion / duration commitment exactly as stored, beside what the
requirement expects; where they differ -- or where a later deadline
extension left the commitment before offers close -- it's flagged, never
changed; the same in the offer page and the comparison."""
from datetime import date, timedelta

from tests.test_stage4_9_participation import _account, _when

DECL = "I have visited the site."


def _d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _tender(owner, **timing):
    data = {"title": "Fit-out", "address": "Kaifan", "description": "Office fit-out.", "bid_deadline": _when(10), **timing}
    pid = owner.post("/projects", data=data).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"declarations": [DECL]})
    r = owner.post(f"/owner/projects/{pid}/publish")
    assert r.status_code == 200, r.text
    return pid


def _submit(sp, pid, **timing):
    sp.post(f"/projects/{pid}/participate")
    r = sp.put(f"/projects/{pid}/offers/draft", json={"amount": "1000", "accepted_declarations": [DECL], **timing})
    assert r.status_code == 200, r.text
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_commitments_as_stored_beside_the_requirements_timing(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner, expected_start_date=_d(20), expected_duration_days="30")
    a_id = _submit(a, pid, proposed_start_date=_d(20), proposed_duration_days=30)
    b_id = _submit(b, pid, proposed_start_date=_d(25), proposed_completion_date=_d(70))
    d = owner.get(f"/owner/projects/{pid}/offers/{b_id}").json()
    o, req = d["offer"], d["requirement"]
    assert (o["proposed_start_date"], o["proposed_completion_date"], o["proposed_duration_days"]) == (_d(25), _d(70), None)
    assert (req["expected_start_date"], req["expected_duration_days"], req["expected_completion_date"]) == (_d(20), 30, None)
    # Differences flagged, values untouched: B starts later, finishes later and takes 45 days against 30.
    assert sorted(o["timing_conflicts"]) == ["finishes_later", "starts_later", "takes_longer"]
    assert owner.get(f"/owner/projects/{pid}/offers/{a_id}").json()["offer"]["timing_conflicts"] == []
    # The comparison shows the same stored commitments and flags.
    compared = owner.get(f"/owner/projects/{pid}/offers/compare", params=[("ids", a_id), ("ids", b_id)]).json()
    assert [(x["proposed_start_date"], x["proposed_completion_date"], x["proposed_duration_days"], sorted(x["timing_conflicts"])) for x in compared["offers"]] == [
        (_d(20), None, 30, []), (_d(25), _d(70), None, ["finishes_later", "starts_later", "takes_longer"])]
    assert compared["requirement"]["expected_start_date"] == _d(20)


def test_nothing_is_forced_where_the_requirement_sets_no_timing(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    offer_id = _submit(sp, pid)
    o = owner.get(f"/owner/projects/{pid}/offers/{offer_id}").json()["offer"]
    assert (o["proposed_start_date"], o["proposed_completion_date"], o["proposed_duration_days"], o["timing_conflicts"]) == (None, None, None, [])


def test_a_moved_deadline_or_an_amendment_is_flagged_not_rewritten(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner, expected_start_date=_d(20))
    a_id = _submit(a, pid, proposed_start_date=_d(12), proposed_duration_days=30)
    # An extension (not a material change) moves offers' close past A's start: A's offer stays current, its start is flagged.
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(15)}, headers={"If-Match": str(v)}).status_code == 200
    d = owner.get(f"/owner/projects/{pid}/offers/{a_id}").json()
    assert d["on_current_version"] is True and "before_close" in d["offer"]["timing_conflicts"]
    assert d["offer"]["proposed_start_date"] == _d(12)  # never moved
    # A material amendment of the expected start: A's commitment answered the earlier version and is shown as such.
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"expected_start_date": _d(16)}, headers={"If-Match": str(v)}).status_code == 200
    d = owner.get(f"/owner/projects/{pid}/offers/{a_id}").json()
    assert (d["on_current_version"], d["offer"]["based_on_material_revision"], d["offer"]["proposed_start_date"]) == (False, 0, _d(12))
    assert owner.get(f"/projects/{pid}/versions/0").json()["fields"]["expected_start_date"] == _d(20)
    # A revises: the current commitment is the revision; the original is kept in the history.
    r = a.post(f"/projects/{pid}/offers", json={"amount": "1000", "accepted_declarations": [DECL], "proposed_start_date": _d(16), "proposed_duration_days": 28}, headers={"If-Match": "1"})
    assert r.status_code == 200, r.text
    d = owner.get(f"/owner/projects/{pid}/offers/{a_id}").json()
    assert (d["offer"]["proposed_start_date"], d["offer"]["proposed_duration_days"], d["offer"]["timing_conflicts"], d["on_current_version"]) == (_d(16), 28, [], True)
    assert [(h["proposed_start_date"], h["proposed_duration_days"]) for h in owner.get(f"/owner/projects/{pid}/offers/{a_id}/history").json()] == [(_d(12), 30)]
    # Withdrawn: no longer a commitment the owner is shown; a competitor never sees it.
    b_id = _submit(b, pid, proposed_start_date=_d(18), proposed_duration_days=20)
    assert b.get(f"/owner/projects/{pid}/offers/{a_id}").status_code == 403
    assert _d(16) not in b.get(f"/projects/{pid}/offers/mine").text.replace(_d(18), "")
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    row = next(x for x in owner.get(f"/owner/projects/{pid}/offers").json() if x["id"] == b_id)
    assert (row["status"], row["proposed_start_date"], row["proposed_duration_days"]) == ("withdrawn", None, None)

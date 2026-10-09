"""Stage 5.16: a provider's own offers across requirements -- one entry per
offer (drafts apart, under "preparing"), each with its status, the
requirement's outcome and when it was submitted/changed; the full offer and
its earlier versions openable after offers close; only their own side's;
bounded."""
from datetime import datetime, timedelta

from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _when

DECL = "I have visited the site."


def _tender(owner, title):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Substation works.", "bid_deadline": _when(10)}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _submit(sp, pid, amount="1000", method="Method v1"):
    sp.post(f"/projects/{pid}/participate")
    sp.put(f"/projects/{pid}/offers/draft", json={"amount": amount, "message": method, "accepted_declarations": [DECL]})
    r = sp.post(f"/projects/{pid}/offers/draft/submit")
    assert r.status_code == 200, r.text
    return r.json()


def test_one_entry_per_offer_with_status_outcome_and_timing(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    pids = {t: _tender(owner, t) for t in ("open", "revised", "withdrawn", "awarded", "lost", "canceled", "external", "expired", "suspended", "drafting")}
    rival = _account(db, "service_provider", "rival@example.com")
    for t, pid in pids.items():
        if t != "drafting":
            _submit(sp, pid)
    sp.post(f"/projects/{pids['drafting']}/participate")  # only a draft
    sp.post(f"/projects/{pids['revised']}/offers", json={"amount": "900", "message": "Method v2", "accepted_declarations": [DECL]}, headers={"If-Match": "1"})
    sp.post(f"/projects/{pids['withdrawn']}/offers/withdraw")
    _submit(rival, pids["lost"], "800")
    for t in ("awarded", "lost", "expired"):
        db.get(Project, pids[t]).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    sp.get("/service-provider/feed")
    mine_awarded = next(o for o in sp.get("/service-provider/my-bids").json() if o["project_id"] == pids["awarded"])
    assert owner.post(f"/owner/projects/{pids['awarded']}/offers/{mine_awarded['offer_id']}/approve").status_code == 200
    rival_offer = rival.get(f"/projects/{pids['lost']}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pids['lost']}/offers/{rival_offer}/approve").status_code == 200
    owner.post(f"/owner/projects/{pids['canceled']}/cancel", json={"reason": "not_needed"})
    db.get(Project, pids["external"]).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    sp.get("/service-provider/feed")
    owner.post(f"/owner/projects/{pids['external']}/close-externally", json={})
    admin.post(f"/admin/projects/{pids['suspended']}/suspend", json={"suspended": True})

    bids = {b["project_id"]: b for b in sp.get("/service-provider/my-bids").json()}
    # One entry per offer; the draft is under "preparing", not here.
    assert set(bids) == {pid for t, pid in pids.items() if t != "drafting"}
    assert [p["project_id"] for p in sp.get("/service-provider/preparing").json()] == [pids["drafting"]]
    got = {t: (bids[pid]["offer_status"], bids[pid]["project_status"], bids[pid]["closure_reason"], bids[pid]["project_suspended"]) for t, pid in pids.items() if t != "drafting"}
    assert got == {
        "open": ("submitted", "open", None, False),
        "revised": ("submitted", "open", None, False),
        "withdrawn": ("withdrawn", "open", None, False),
        "awarded": ("approved", "awarded", None, False),
        "lost": ("rejected", "awarded", None, False),
        "canceled": ("closed", "canceled", "not_needed", False),  # Batch B: live offers end "closed"
        "external": ("closed", "no_award", "closed_externally", False),  # Batch B: live offers end "closed"
        "expired": ("submitted", "closed", None, False),
        "suspended": ("submitted", "open", None, True),
    }, got
    # Timing: first submitted, and the last change; UTC instants; revisions counted.
    r = bids[pids["revised"]]
    assert r["submitted_at"].endswith("Z") and r["updated_at"].endswith("Z") and r["revision"] == 2 and r["amount"] == "900.000"
    assert bids[pids["withdrawn"]]["revision"] == 2
    # Nothing of anyone else's offer is in the provider's list.
    # (amounts compared exactly: "800" can occur inside a random id)
    assert all(b["amount"] != "800.000" for b in bids.values()) and all(b["offer_id"] != rival_offer for b in bids.values())


def test_the_full_offer_and_its_versions_stay_openable_after_offers_close(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com")
    pid = _tender(owner, "Closed")
    _submit(sp, pid)
    sp.post(f"/projects/{pid}/offers", json={"amount": "900", "message": "Method v2", "accepted_declarations": [DECL], "assumptions": "Excludes civils."}, headers={"If-Match": "1"})
    _submit(rival, pid, "800", "Rival method")
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    sp.get("/service-provider/feed")
    # The provider can still open the requirement, their offer in full, and its earlier version.
    assert sp.get(f"/projects/{pid}").status_code == 200
    preview = sp.get(f"/projects/{pid}/offers/draft/preview").json()
    assert (preview["offer"]["amount"], preview["offer"]["message"], preview["offer"]["assumptions"], preview["offer"]["status"]) == ("900.000", "Method v2", "Excludes civils.", "submitted")
    history = sp.get(f"/projects/{pid}/offers/mine/history").json()
    assert [(h["revision_number"], h["amount"], h["message"]) for h in history] == [(1, "1000.000", "Method v1")]
    # Never the competitor's.
    assert "Rival method" not in str(preview) and "Rival method" not in str(history)


def test_bounded_and_only_ones_own(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    other = _account(db, "service_provider", "other@example.com")
    pids = [_tender(owner, f"R{i}") for i in range(3)]
    for pid in pids:
        _submit(boss, pid)
    # Organization members share the list; another provider has none of it.
    assert len(eng.get("/service-provider/my-bids").json()) == 3 and other.get("/service-provider/my-bids").json() == []
    assert other.get("/service-provider/my-bids", params={"offer_id": "x", "service_provider_id": boss.get("/auth/me").json()["id"]}).json() == []
    # Bounded and pageable, most recent first, without repeats.
    page1 = boss.get("/service-provider/my-bids", params={"limit": 2}).json()
    page2 = boss.get("/service-provider/my-bids", params={"limit": 2, "offset": 2}).json()
    assert len(page1) == 2 and len(page2) == 1 and not ({b["offer_id"] for b in page1} & {b["offer_id"] for b in page2})
    for bad in ({"limit": 0}, {"limit": 501}, {"offset": -1}):
        assert boss.get("/service-provider/my-bids", params=bad).status_code == 422

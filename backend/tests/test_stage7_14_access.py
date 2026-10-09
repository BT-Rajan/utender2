"""Stage 7.14: post-award access. Every post-award endpoint -- agreement,
documents and their files, execution, deliverables, changes, completion,
history -- is decided on the server, per request, from the caller's current
membership of the owner side or the winning provider's side. Everyone else
(losing bidders, other organisations, a removed member, a suspended winner,
the signed-out) is refused on every child endpoint, whatever ids they send;
the winner never reaches the owner's Stage 6 evaluation records or a losing
offer; admins read but never write; completion leaves reading intact and
writing closed."""
from fastapi.testclient import TestClient

from app.main import app
from app.models.offer import Offer, OfferDocument
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import put_in_force
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _submitted, _tender

PDF = ("paper.pdf", b"%PDF paper", "application/pdf")


def _v(client, pid):
    return {"If-Match": str(client.get(f"/projects/{pid}/agreement").json()["version"])}


def _world(db):
    fahad, noura, fahad_id, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, amal_id, sami_id = _organization(db, "service_provider", "Amal Contracting", "amal@amal.example", "sami@amal.example")
    loser = _account(db, "service_provider", "badr@example.com")
    pid = _tender(fahad)
    _submitted(amal, pid)
    _submitted(loser, pid)
    fahad.post(f"/owner/projects/{pid}/close")
    wid = amal.get(f"/projects/{pid}/offers/mine").json()["id"]
    lid = loser.get(f"/projects/{pid}/offers/mine").json()["id"]
    fahad.put(f"/owner/projects/{pid}/offers/{lid}/shortlist")
    fahad.post(f"/owner/projects/{pid}/notes", json={"body": "Badr cheaper but weak method.", "offer_id": lid})
    assert fahad.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    mid = noura.post(f"/projects/{pid}/agreement/milestones", json={"title": "Panels"}, headers=_v(noura, pid)).json()["milestones"][0]["id"]
    doc = fahad.post(f"/projects/{pid}/agreement/documents", data={"kind": "signed_agreement"}, files={"file": PDF}).json()["documents"][0]["id"]
    put_in_force(fahad, amal, pid)  # Batch A: effective today (Kuwait), the provider confirms, the owner activates
    sami.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(sami, pid))  # a member, not the representative
    vid = sami.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra.", "value_change": "100"}, headers=_v(sami, pid)).json()["variations"][0]["id"]
    return dict(fahad=fahad, noura=noura, amal=amal, sami=sami, loser=loser, pid=pid, wid=wid, lid=lid, mid=mid, doc=doc, vid=vid,
                fahad_id=fahad_id, amal_id=amal_id, sami_id=sami_id)


def _every_post_award_call(client, w):
    p, m, d, v = w["pid"], w["mid"], w["doc"], w["vid"]
    base = f"/projects/{p}/agreement"
    return [
        client.get(base),
        client.get(f"{base}/documents/{d}/file", follow_redirects=False),
        client.patch(base, json={"reference": "x"}),
        client.post(f"{base}/activate"),
        client.post(f"{base}/terminate", json={"reason": "x"}),
        client.post(f"{base}/start-work", json={}),
        client.post(f"{base}/progress", json={"action": "hold"}),
        client.post(f"{base}/documents", data={"kind": "progress_photo"}, files={"file": PDF}),
        client.delete(f"{base}/documents/{d}"),
        client.post(f"{base}/milestones", json={"title": "x"}),
        client.patch(f"{base}/milestones/{m}", json={"title": "x"}),
        client.delete(f"{base}/milestones/{m}"),
        client.post(f"{base}/milestones/{m}/deliver", json={}),
        client.post(f"{base}/milestones/{m}/accept", json={}),
        client.post(f"{base}/milestones/{m}/return", json={"note": "x"}),
        client.post(f"{base}/variations", json={"description": "x"}),
        client.post(f"{base}/variations/{v}/agree", json={}),
        client.post(f"{base}/variations/{v}/reject", json={}),
        client.post(f"{base}/variations/{v}/withdraw"),
        client.post(f"{base}/completion/submit", json={}),
        client.post(f"{base}/completion/accept", json={}),
        client.post(f"{base}/completion/return", json={"note": "x"}),
    ]


def test_outsiders_are_refused_on_every_post_award_endpoint(db):
    w = _world(db)
    rival_owner = _account(db, "owner", "other@example.com", organization="Other Co")
    rival_sp = _account(db, "service_provider", "rival@example.com", organization="Rival Contracting")
    for who, client in (("loser", w["loser"]), ("rival owner", rival_owner), ("rival provider", rival_sp)):
        for r in _every_post_award_call(client, w):
            assert r.status_code == 404, (who, r.request.method, r.request.url.path, r.status_code)
    for r in _every_post_award_call(TestClient(app), w):
        assert r.status_code == 401, (r.request.method, r.request.url.path)
    # The losing bidder keeps only "awarded to a successful bidder".
    award = w["loser"].get(f"/projects/{w['pid']}/award").json()
    assert all(award[k] is None for k in ("id", "offer_id", "amount", "owner_name", "service_provider_company_name"))


def test_both_sides_every_member_and_admin_read_only(db):
    w = _world(db)
    admin = _admin(db)
    for client in (w["fahad"], w["noura"], w["amal"], w["sami"], admin):
        seen = client.get(f"/projects/{w['pid']}/agreement")
        assert seen.status_code == 200 and seen.json()["variations"][0]["id"] == w["vid"]
        assert client.get(f"/projects/{w['pid']}/agreement/documents/{w['doc']}/file", follow_redirects=False).status_code == 303
    writes = _every_post_award_call(admin, w)[2:]
    assert all(r.status_code == 403 for r in writes), [(r.request.url.path, r.status_code) for r in writes if r.status_code != 403]
    # A role can't be borrowed: the winner can't do the owner's part, nor the owner the provider's.
    base = f"/projects/{w['pid']}/agreement"
    # Batch A: either party may now terminate, so the owner-only step checked here is putting the agreement in force.
    assert w["sami"].post(f"{base}/activate", headers={}).status_code == 403
    assert w["sami"].post(f"{base}/variations/{w['vid']}/agree", json={}, headers={}).status_code == 403  # its own side's proposal
    assert w["noura"].post(f"{base}/milestones/{w['mid']}/deliver", json={}, headers={}).status_code == 403


def test_the_winner_never_reaches_stage6_records_or_a_losing_offer(db):
    w = _world(db)
    p, lid = w["pid"], w["lid"]
    loser_doc = db.query(OfferDocument).filter(OfferDocument.offer_id == lid).one().id
    for client in (w["amal"], w["sami"]):
        for path in (f"/owner/projects/{p}/offers", f"/owner/projects/{p}/offers/{lid}", f"/owner/projects/{p}/offers/{lid}/history",
                     f"/owner/projects/{p}/offers/{lid}/clarifications", f"/owner/projects/{p}/notes", f"/owner/projects/{p}/offers/{lid}/shortlist",
                     f"/owner/projects/{p}/offers/compare?ids={lid}", f"/owner/projects/{p}/offers/{lid}/documents/file?label=Method%20statement"):
            assert client.get(path, follow_redirects=False).status_code in (403, 404), path
        assert client.get(f"/projects/{p}/offers/documents/{loser_doc}/file", follow_redirects=False).status_code == 404
        body = client.get(f"/projects/{p}/agreement").text + client.get(f"/projects/{p}/award").text
        assert lid not in body and "Badr cheaper" not in body and "badr" not in body.lower()  # nothing of the losing offer or the notes
    assert w["fahad"].get(f"/owner/projects/{p}/notes").status_code == 200  # the owner keeps its own evaluation records


def test_access_follows_current_membership_and_standing(db):
    w = _world(db)
    p = w["pid"]
    # A removed member of the winning organisation: refused from the next request on, reads and writes.
    assert w["amal"].delete(f"/account/organization/members/{w['sami_id']}").status_code == 200
    for r in _every_post_award_call(w["sami"], w):
        assert r.status_code == 404, (r.request.method, r.request.url.path, r.status_code)
    assert w["amal"].get(f"/projects/{p}/agreement").status_code == 200  # the organisation keeps it
    # The winning organisation suspended: out of sight entirely; back when reinstated.
    profile = db.get(ServiceProviderProfile, w["amal_id"])
    profile.is_suspended = True
    db.commit()
    assert w["amal"].get(f"/projects/{p}/agreement").status_code == 404
    assert w["amal"].post(f"/projects/{p}/agreement/progress", json={"action": "update", "note": "x"}).status_code == 404
    profile.is_suspended = False
    db.commit()
    assert w["amal"].get(f"/projects/{p}/agreement").status_code == 200
    # The owner organisation suspended: keeps reading its own record, can't change it (existing owner policy).
    owner_profile = db.get(OwnerProfile, w["fahad_id"])
    owner_profile.is_suspended = True
    db.commit()
    assert w["noura"].get(f"/projects/{p}/agreement").status_code == 200
    assert w["noura"].post(f"/projects/{p}/agreement/progress", json={"action": "update", "note": "x"}, headers={}).status_code == 403
    owner_profile.is_suspended = False
    db.commit()
    # Signed out: the old session no longer works.
    assert w["sami"].post("/auth/logout").status_code in (200, 204)
    assert w["sami"].get(f"/projects/{p}/agreement").status_code == 401


def test_completed_reads_stay_writes_close(db):
    w = _world(db)
    p, base = w["pid"], f"/projects/{w['pid']}/agreement"
    w["sami"].post(f"{base}/variations/{w['vid']}/withdraw", headers={})
    m = w["amal"].get(base).json()["milestones"][0]
    w["amal"].post(f"{base}/milestones/{w['mid']}/deliver", json={}, headers={"If-Match": str(m["version"])})
    m = w["fahad"].get(base).json()["milestones"][0]
    w["fahad"].post(f"{base}/milestones/{w['mid']}/accept", json={}, headers={"If-Match": str(m["version"])})
    assert w["amal"].post(f"{base}/completion/submit", json={}, headers=_v(w["amal"], p)).status_code == 200
    assert w["noura"].post(f"{base}/completion/accept", json={}, headers=_v(w["noura"], p)).status_code == 200
    for client in (w["fahad"], w["sami"]):
        assert client.get(base).json()["status"] == "completed"
        assert client.get(f"{base}/documents/{w['doc']}/file", follow_redirects=False).status_code == 303
        writes = _every_post_award_call(client, w)[2:]
        assert all(r.status_code in (403, 409) for r in writes), [(r.request.url.path, r.status_code) for r in writes if r.status_code not in (403, 409)]
    assert w["loser"].get(base).status_code == 404  # completion opens nothing to others
    db.expire_all()
    assert db.get(Offer, w["lid"]).amount is not None  # the losing offer stays on record, unseen

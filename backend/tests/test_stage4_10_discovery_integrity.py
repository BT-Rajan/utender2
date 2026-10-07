"""Stage 4.10: the whole provider journey -- discover, find, understand,
eligibility, documents, clarify, save, decide -- on one requirement as its
owner pauses, resumes, extends, amends and ends it; and every way round it
(other ids, other organizations, direct calls, stale pages, old links,
manipulated parameters) refused by the server."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.clarification import Clarification
from app.models.enums import UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.participation import Participation
from app.models.project import Project
from app.models.saved_opportunity import SavedOpportunity
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _account(db, role, email, organization=None, approve=True):
    c = TestClient(app)
    uid = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role}).json()["id"]
    c.put("/account/stakeholder", json={"type": "organization", "legal_name": organization, "authorized": True} if organization else {"type": "individual"})
    if approve:
        model = OwnerProfile if role == "owner" else ServiceProviderProfile
        p = db.get(model, uid)
        p.verification_status = VerificationStatus.approved
        if role == "service_provider":
            p.company_name = email.split("@")[0]
            p.payment_override_active = True
        db.commit()
    return c, uid


def _get(client, url):
    return client.get("/" + url.split("://", 1)[-1].split("/", 1)[-1])


def _state(sp, pid):
    """What the provider is shown and can do, from the server."""
    d = sp.get(f"/projects/{pid}")
    return d.status_code, (d.json()["participation"] if d.status_code == 200 else sp.get(f"/projects/{pid}/eligibility").json()["participation"])


def test_the_journey_through_every_change(db):
    owner, _ = _account(db, "owner", "owner@example.com")
    sp, sp_id = _account(db, "service_provider", "noor@example.com")
    rival, _ = _account(db, "service_provider", "rival@example.com")
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="A"))
    db.commit()
    admin = TestClient(app)
    admin.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    pid = owner.post(
        "/projects",
        data={"title": "Villa rewiring", "address": "Kaifan, block 4, house 12", "governorate": "capital", "area": "Kaifan", "trade": "Electrical",
              "description": "Rewire a villa: 40 points and a new DB board.", "bid_deadline": _when(10), "status": "open"},
        files=[("drawings", ("single-line.pdf", b"%PDF-v1", "application/pdf"))],
    ).json()["id"]

    # Discover -> find -> the same requirement in summary and in full.
    card = next(p for p in sp.get("/service-provider/feed", params={"search": "rewiring", "governorate": "capital", "sort": "newest"}).json()["items"] if p["id"] == pid)
    full = sp.get(f"/projects/{pid}").json()
    for field in ("title", "trade", "governorate", "area", "bid_deadline", "tender_type", "status"):
        assert card[field] == full[field], field
    assert card["address"] is None and full["address"] == "Kaifan, block 4, house 12"
    assert full["participation"]["status"] == "can_participate"
    # 1. Documents, questions, save, decide.
    doc = full["drawings"][0]["url"]
    assert _get(sp, doc).content == b"%PDF-v1"
    qid = sp.post(f"/projects/{pid}/clarifications", json={"question": "Garage included?"}).json()["id"]
    sp.put(f"/service-provider/saved/{pid}")
    assert sp.post(f"/projects/{pid}/participate").json()["started"] is True

    # 2-3. Suspended by U-Tender: the provider, refreshing, gets nothing active and nothing about it.
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True})
    code, verdict = _state(sp, pid)
    assert code == 404 and verdict["availability"] == "unavailable"
    assert all(p["id"] != pid for p in sp.get("/service-provider/feed").json()["items"])
    assert next(s for s in sp.get("/service-provider/saved").json() if s["id"] == pid)["availability"] == "unavailable"
    for attempt in (sp.post(f"/projects/{pid}/participate"), sp.post(f"/projects/{pid}/offers", json={"amount": "900"}),
                    sp.post(f"/projects/{pid}/clarifications", json={"question": "Still?"}), sp.get(f"/projects/{pid}/drawings-zip")):
        assert attempt.status_code in (400, 404)
    assert sp.get("/service-provider/preparing").json() == []
    # 4. Resumed: back, as it was.
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": False})
    assert _state(sp, pid)[1]["status"] == "can_participate"
    # 5. Extended: the one current deadline everywhere.
    v = owner.get(f"/projects/{pid}").json()["version"]
    later = _when(20)
    owner.patch(f"/projects/{pid}", json={"bid_deadline": later}, headers={"If-Match": str(v)})
    assert sp.get(f"/projects/{pid}").json()["bid_deadline"] == later
    assert next(p for p in sp.get("/service-provider/feed").json()["items"] if p["id"] == pid)["bid_deadline"] == later
    assert next(s for s in sp.get("/service-provider/saved").json() if s["id"] == pid)["bid_deadline"] == later
    # 6-9. A material amendment (the drawing replaced) after the download, the question and the decision.
    owner.post(f"/projects/{qid and pid}/clarifications/{qid}/answer", json={"answer": "No."})
    owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("single-line.pdf", b"%PDF-v2", "application/pdf"))])
    now = sp.get(f"/projects/{pid}").json()
    assert now["material_revision"] == 1 and now["participation"]["seen_material_revision"] == 0  # flagged, not silently current
    assert _get(sp, now["drawings"][0]["url"]).content == b"%PDF-v2"
    v0 = {d["file_name"]: d for d in sp.get(f"/projects/{pid}/versions/0").json()["documents"]}
    assert _get(sp, v0["single-line.pdf"]["url"]).content == b"%PDF-v1"  # what was first downloaded is on record
    assert sp.get("/service-provider/preparing").json()[0]["changed_since"] is True
    assert [c["answer"] for c in sp.get(f"/projects/{pid}/clarifications").json()] == ["No."]
    # The offer is made against the current version.
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "900"}).json()["based_on_material_revision"] == 1
    # 10. The owner cancels while the provider's page is open: nothing on it still works.
    owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "postponed"})
    for attempt in (sp.post(f"/projects/{pid}/participate"), sp.post(f"/projects/{pid}/offers", json={"amount": "800"}),
                    sp.post(f"/projects/{pid}/clarifications", json={"question": "Why?"}), sp.post(f"/projects/{pid}/offers/withdraw")):
        assert attempt.status_code == 400
    assert sp.put(f"/service-provider/saved/{pid}").status_code == 404 and pid in [s["id"] for s in sp.get("/service-provider/saved").json()]
    code, verdict = _state(sp, pid)
    assert code == 200 and verdict["availability"] == "ended"  # the bidder keeps sight of it
    assert rival.get(f"/projects/{pid}").status_code == 404  # who never took part: nothing
    # 11. Expiry of another, at the deadline: the same.
    other = owner.post("/projects", data={"title": "Fence", "address": "x", "description": "Paint a fence.", "bid_deadline": _when(3), "status": "open"}).json()["id"]
    sp.put(f"/service-provider/saved/{other}")
    db.get(Project, other).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert all(p["id"] != other for p in sp.get("/service-provider/feed").json()["items"])
    assert next(s for s in sp.get("/service-provider/saved").json() if s["id"] == other)["availability"] == "ended"
    assert sp.post(f"/projects/{other}/participate").status_code == 400


def test_no_way_round_the_rules(db):
    owner, owner_id = _account(db, "owner", "owner@example.com")
    sp, sp_id = _account(db, "service_provider", "noor@example.com")
    rival, rival_id = _account(db, "service_provider", "rival@example.com", organization="Rival Co")
    pid = owner.post("/projects", data={"title": "Villa", "address": "x", "description": "Rewire.", "bid_deadline": _when(9), "status": "open"},
                     files=[("drawings", ("plan.pdf", b"%PDF", "application/pdf"))]).json()["id"]
    restricted = owner.post("/projects", data={"title": "Orgs only", "address": "secret plot", "description": "HV.", "bid_deadline": _when(9)},
                            files=[("drawings", ("hv.pdf", b"%PDF-hv", "application/pdf"))]).json()["id"]
    owner.put(f"/projects/{restricted}/eligibility", json={"provider_type": "organization"})
    owner.post(f"/owner/projects/{restricted}/publish")
    draft = owner.post("/projects", data={"title": "Draft", "address": "x", "bid_deadline": _when(9)}).json()["id"]

    # Other ids in the body are ignored: the server decides who.
    sp.post(f"/projects/{pid}/clarifications", json={"question": "Q?", "service_provider_id": rival_id, "organization_id": "x"})
    assert db.query(Clarification).one().service_provider_id == sp_id
    sp.post(f"/projects/{pid}/participate", json={"service_provider_id": rival_id})
    sp.put(f"/service-provider/saved/{pid}", json={"service_provider_id": rival_id})
    assert {p.service_provider_id for p in db.query(Participation)} == {sp_id} and {s.service_provider_id for s in db.query(SavedOpportunity)} == {sp_id}
    # Another provider's or organization's private things: not theirs to see or change.
    assert rival.get("/service-provider/saved").json() == [] and rival.get("/service-provider/preparing").json() == []
    assert rival.get(f"/projects/{pid}").json()["participation"]["started"] is False
    rival.delete(f"/service-provider/saved/{pid}")
    assert db.query(SavedOpportunity).count() == 1
    # Restricted or unpublished: not by id, search, filter, page, save, decide, question or file.
    for target in (restricted, draft):
        for attempt in (sp.get(f"/projects/{target}"), sp.get(f"/projects/{target}/drawings-zip"), sp.get(f"/projects/{target}/drawings/history"),
                        sp.get(f"/projects/{target}/versions/0"), sp.get(f"/projects/{target}/clarifications"), sp.put(f"/service-provider/saved/{target}")):
            assert attempt.status_code in (403, 404), (target, attempt.request.url)
        assert sp.post(f"/projects/{target}/participate").status_code in (403, 404)
    for params in ({"search": "Orgs only"}, {"search": "secret plot"}, {"offset": 0, "limit": 50}, {"sort": "newest", "offset": 1}, {"min_days": 0, "accepting": True}):
        assert all(p["id"] not in (restricted, draft) for p in sp.get("/service-provider/feed", params=params).json()["items"])
    for bad in ({"limit": 1000}, {"offset": -1}, {"sort": "price"}, {"min_days": 9999}, {"search": "x" * 500}):
        assert sp.get("/service-provider/feed", params=bad).status_code == 422, bad
    # An old link for a file it was never given: refused.
    url = owner.get(f"/projects/{restricted}").json()["drawings"][0]["url"]
    assert _get(sp, url.replace("hv.pdf", "plan.pdf")).status_code == 403
    # A suspended provider account is told why.
    db.get(ServiceProviderProfile, sp_id).is_suspended = True
    db.commit()
    r = sp.post(f"/projects/{pid}/participate")
    assert r.status_code == 403 and "suspended" in r.json()["detail"]

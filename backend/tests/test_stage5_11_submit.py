"""Stage 5.11: submitting the offer -- the stored draft, exactly as previewed,
becomes the formal offer in one server-side step under the requirement's
lock, after every check is made again at that moment (the Stage 5.8 gate);
or nothing changes. Once only; the owner gets it through the existing offer
list (sealed rules intact); competitors never see it."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import NotificationType, OfferStatus, TenderType
from app.models.notification import Notification
from app.models.offer import Offer, OfferRevision
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin, _when

needs_mysql = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs real row locking (MySQL)")

SUBMIT = "/projects/{}/offers/draft/submit"
SAVE = "/projects/{}/offers/draft"
DECL = "I have visited the site."
RULES = {"approach": "required", "documents": [{"name": "Method statement", "required": True}], "declarations": [DECL]}
FORM = {"amount": "12500", "message": "Isolate, swap, test.", "accepted_declarations": [DECL], "assumptions": "Excludes civil works."}


def _d(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _tender(owner, title="Substation", sealed=False):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "HV works.", "bid_deadline": _when(10),
                                       "tender_type": "sealed" if sealed else "owner_visible"}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json=RULES)
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _ready(sp, pid, form=FORM):
    sp.post(f"/projects/{pid}/participate")
    assert sp.put(SAVE.format(pid), json=form).status_code == 200
    assert sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": ("m.pdf", b"%PDF", "application/pdf")}).status_code == 200
    return sp.get(f"/projects/{pid}/offers/mine").json()["draft_version"]


def test_complete_offer_is_submitted_once_and_reaches_the_owner(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com")
    pid = _tender(owner)
    version = _ready(sp, pid)
    draft_id = db.query(Offer).one().id
    # 1. Submitted: the same row, now an offer, with when; exactly the stored content.
    r = sp.post(SUBMIT.format(pid), headers={"If-Match": str(version)})
    assert r.status_code == 200, r.text
    offer = r.json()
    assert (offer["id"], offer["status"], offer["revision"], offer["message"], offer["assumptions"], offer["declarations_accepted"]) == (
        draft_id, "submitted", 1, "Isolate, swap, test.", "Excludes civil works.", [DECL])
    assert offer["submitted_at"] and offer["submitted_at"].endswith("Z") and db.query(OfferRevision).count() == 0
    # 11. The provider sees it as submitted (and among their bids, no longer "preparing").
    assert sp.get(f"/projects/{pid}/offers/mine").json()["status"] == "submitted"
    assert [b["project_id"] for b in sp.get("/service-provider/my-bids").json()] == [pid] and sp.get("/service-provider/preparing").json() == []
    assert sp.get(f"/projects/{pid}").json()["participation"]["offer_status"] == "submitted"
    # 12. The owner gets it through the existing offer list, and one "new offer" notice.
    listed = owner.get(f"/owner/projects/{pid}/offers").json()
    assert [(o["id"], o["amount"], o["submitted_at"] is not None) for o in listed] == [(draft_id, "12500.000", True)]
    owner_id = owner.get("/auth/me").json()["id"]
    assert db.query(Notification).filter(Notification.user_id == owner_id, Notification.type == NotificationType.bid_submitted).count() == 1
    assert db.get(Project, pid).tender_type_locked is True
    # 8/9. Again (double-click, retry, another tab): refused, still one offer, no second notice.
    for _ in range(2):
        again = sp.post(SUBMIT.format(pid), headers={"If-Match": str(version)})
        assert again.status_code == 409 and "already been submitted" in again.json()["detail"]
    assert db.query(Offer).count() == 1 and db.query(Notification).filter(Notification.user_id == owner_id, Notification.type == NotificationType.bid_submitted).count() == 1
    # 13. A competitor: their own offer only (none), and no route to this one.
    assert rival.get(f"/projects/{pid}/offers/mine").json() is None
    assert rival.get(f"/projects/{pid}/offers/draft/preview").status_code == 404
    assert rival.get(f"/owner/projects/{pid}/offers").status_code == 403
    # A later revision goes through the existing route, kept in history, and the owner is told it was revised.
    sp.post(f"/projects/{pid}/offers", json={"amount": "12000", "message": "Isolate, swap, test.", "accepted_declarations": [DECL]})
    assert db.query(OfferRevision).count() == 1 and sp.get(f"/projects/{pid}/offers/mine").json()["submitted_at"] == offer["submitted_at"]
    assert db.query(Notification).filter(Notification.user_id == owner_id, Notification.type == NotificationType.bid_revised).count() == 1


def test_incomplete_or_ineligible_is_refused_and_the_draft_is_kept(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    sp.post(f"/projects/{pid}/participate")
    sp.put(SAVE.format(pid), json={"amount": "12500"})
    # 2/14. Incomplete: refused with what's missing; still a draft with what was saved.
    r = sp.post(SUBMIT.format(pid))
    assert r.status_code == 400 and "technical approach" in r.json()["detail"] and "Method statement" in r.json()["detail"]
    row = db.query(Offer).one()
    db.refresh(row)
    assert (row.status, row.submitted_at, row.amount) == (OfferStatus.draft, None, 12500)
    assert owner.get(f"/owner/projects/{pid}/offers").json() == [] and db.get(Project, pid).tender_type_locked is False
    # Invalid timing saved earlier, made invalid by a deadline extension: refused.
    version = _ready(sp, pid, {**FORM, "proposed_start_date": _d(20), "proposed_duration_days": 10})
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(25)}, headers={"If-Match": str(v)})
    r = sp.post(SUBMIT.format(pid), headers={"If-Match": str(version)})
    assert r.status_code == 400 and "before the response deadline" in r.json()["detail"]
    sp.put(SAVE.format(pid), json={**FORM, "proposed_start_date": _d(30), "proposed_duration_days": 10})
    # 3. No longer eligible (access lapsed): refused.
    from app.models.service_provider import ServiceProviderProfile
    profile = db.query(ServiceProviderProfile).one()
    profile.payment_override_active = False
    db.commit()
    assert sp.post(SUBMIT.format(pid)).status_code == 403
    profile.payment_override_active = True
    db.commit()
    # A stale page (the draft changed since it was previewed): refused, not submitted unseen.
    current = sp.get(f"/projects/{pid}/offers/mine").json()["draft_version"]
    assert sp.post(SUBMIT.format(pid), headers={"If-Match": str(current - 1)}).status_code == 409
    assert sp.post(SUBMIT.format(pid), headers={"If-Match": str(current)}).status_code == 200


def test_lifecycle_and_amendment_block_submission(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    closed, suspended, expired, at_deadline, canceled, amended = (_tender(owner, t) for t in ("Closed", "Suspended", "Expired", "AtDeadline", "Canceled", "Amended"))
    for pid in (closed, suspended, expired, at_deadline, canceled, amended):
        _ready(sp, pid)
    # Batch B: closing early is refused while a provider is still preparing (sp's draft).
    r = owner.post(f"/owner/projects/{closed}/close")
    assert r.status_code == 409 and "still preparing" in r.json()["detail"]
    # Batch B: the requirement still closes at its deadline with the draft in hand;
    # a rival's submitted offer makes it "closed" (not "expired").
    rival = _account(db, "service_provider", "rival@example.com")
    _ready(rival, closed)
    assert rival.post(SUBMIT.format(closed)).status_code == 200
    db.get(Project, closed).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    assert owner.post(f"/owner/projects/{closed}/close").json()["status"] == "closed"  # 4. closed by the owner
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})  # 5
    db.get(Project, expired).bid_deadline = datetime.utcnow() - timedelta(minutes=1)  # 6/7. deadline passed (server clock)
    # Exactly at the deadline: too late. Whole seconds, as the column stores them
    # (MySQL DATETIME rounds fractions to the nearest second -- possibly forward).
    db.get(Project, at_deadline).bid_deadline = datetime.utcnow().replace(microsecond=0)
    db.commit()
    owner.post(f"/owner/projects/{canceled}/cancel", json={"reason": "not_needed"})
    for pid in (closed, suspended, expired, at_deadline, canceled):
        r = sp.post(SUBMIT.format(pid))
        assert r.status_code == 400, (pid, r.json())
    # A material amendment: not submitted against the old version until reviewed.
    v = owner.get(f"/projects/{amended}").json()["version"]
    owner.patch(f"/projects/{amended}", json={"description": "HV works plus a second transformer."}, headers={"If-Match": str(v)})
    r = sp.post(SUBMIT.format(amended))
    assert r.status_code == 409 and "Review the current requirement" in r.json()["detail"]
    sp.post(f"/projects/{amended}/participate")
    submitted = sp.post(SUBMIT.format(amended)).json()
    assert submitted["status"] == "submitted" and submitted["based_on_material_revision"] == 1
    # Batch B: only sp's own offers -- the rival's offer on `closed` is submitted.
    sp_id = sp.get("/auth/me").json()["id"]
    assert {o.project_id for o in db.query(Offer).filter(Offer.status == OfferStatus.submitted, Offer.service_provider_id == sp_id)} == {amended}
    assert all(o.submitted_at is None for o in db.query(Offer).filter(Offer.status == OfferStatus.draft))


def test_direct_api_and_sealed_tenders(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    rival = _account(db, "service_provider", "rival@example.com")
    pid = _tender(owner, sealed=True)
    # 10. The direct submission route runs the same gate on what it would commit.
    sp.post(f"/projects/{pid}/participate")
    r = sp.post(f"/projects/{pid}/offers", json={"amount": "500", "message": "m", "accepted_declarations": [DECL]})
    assert r.status_code == 400 and "Method statement" in r.json()["detail"]
    assert db.query(Offer).one().status == OfferStatus.draft
    # Another provider can't submit someone else's draft: they have none, whatever is sent.
    offer = db.query(Offer).one()
    assert rival.post(SUBMIT.format(pid), json={"offer_id": offer.id}, params={"offer_id": offer.id}).status_code == 404
    _ready(sp, pid)
    assert sp.post(SUBMIT.format(pid)).status_code == 200
    # Sealed: the owner sees that an offer is in, not what it says or whose it is, until the deadline.
    listed = owner.get(f"/owner/projects/{pid}/offers").json()
    assert len(listed) == 1 and listed[0]["amount"] is None and listed[0]["message"] is None and listed[0]["service_provider_id"] is None
    assert db.get(Project, pid).tender_type == TenderType.sealed


@needs_mysql
def test_two_colleagues_submitting_at_once_make_one_offer(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _account(db, "service_provider", "eng@gulf.example", joining=True)
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    eng.post(f"/account/invitations/{token}/accept")
    pid = _tender(owner)
    _ready(boss, pid)
    clients = [boss, eng]
    for email in ("boss@gulf.example", "eng@gulf.example"):
        c = TestClient(app)
        c.post("/auth/login", json={"email": email, "password": "password123"})
        clients.append(c)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: c.post(SUBMIT.format(pid)), clients))
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409]
    db.expire_all()
    assert db.query(Offer).count() == 1 and db.query(Offer).one().status == OfferStatus.submitted


@needs_mysql
def test_submission_racing_the_owners_close_has_one_outcome(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _tender(owner)
    _ready(sp, pid)
    with ThreadPoolExecutor(2) as pool:
        submit = pool.submit(lambda: sp.post(SUBMIT.format(pid)))
        close = pool.submit(lambda: owner.post(f"/owner/projects/{pid}/close"))
        s, c = submit.result(), close.result()
    db.expire_all()
    offer, project = db.query(Offer).one(), db.get(Project, pid)
    # Batch B: closing early is refused while the draft is still being prepared,
    # so the close can never get in ahead of the submission; the offer always goes in.
    assert s.status_code == 200 and offer.status == OfferStatus.submitted and offer.submitted_at is not None
    if c.status_code == 200:  # submitted first: in, then closed with it (closed, not expired)
        assert project.status.value == "closed"
    else:  # Batch B: close tried first: refused, nothing closed, the offer accepted afterwards
        assert c.status_code == 409 and "still preparing" in c.json()["detail"]
        assert project.status.value == "open"

"""Follow-ups to the Stage 5 audit's limitations: the owner hears of a
withdrawal (anonymously while sealed); a sealed tender doesn't tell
competitors how many offers are in; the provider's dashboard counts are the
server's over all their offers; deadlines are judged by the database's clock
under the requirement's lock."""
from datetime import datetime, timedelta

from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.project import Project
from app.services.tender_lifecycle import bidding_is_open, db_now, lock_project
from tests.test_stage4_9_participation import _account, _when

DECL = "I have visited the site."


def _tender(owner, title, sealed=False):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Substation works.", "bid_deadline": _when(10),
                                       "tender_type": "sealed" if sealed else "owner_visible"}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _submit(sp, pid):
    sp.post(f"/projects/{pid}/participate")
    sp.put(f"/projects/{pid}/offers/draft", json={"amount": "1000", "message": "m", "accepted_declarations": [DECL]})
    assert sp.post(f"/projects/{pid}/offers/draft/submit").status_code == 200


def test_the_owner_hears_of_a_withdrawal_anonymously_while_sealed(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    owner_id = owner.get("/auth/me").json()["id"]
    visible, sealed = _tender(owner, "Visible"), _tender(owner, "Sealed", sealed=True)
    for pid in (visible, sealed):
        _submit(sp, pid)
        assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    notes = {n.link: n.body for n in db.query(Notification).filter(Notification.user_id == owner_id, Notification.type == NotificationType.bid_withdrawn)}
    assert "noor" in notes[f"/owner/projects/{visible}"]
    assert "noor" not in notes[f"/owner/projects/{sealed}"] and "A service provider" in notes[f"/owner/projects/{sealed}"]
    # A refused withdrawal tells no one.
    assert sp.post(f"/projects/{visible}/offers/withdraw").status_code == 400
    assert db.query(Notification).filter(Notification.type == NotificationType.bid_withdrawn).count() == 2


def test_a_sealed_tender_keeps_its_offer_count_from_competitors(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "a@example.com")
    b = _account(db, "service_provider", "b@example.com")
    sealed, visible = _tender(owner, "Sealed", sealed=True), _tender(owner, "Visible")
    for pid in (sealed, visible):
        _submit(a, pid)
    cards = {p["id"]: p for p in b.get("/service-provider/feed").json()["items"]}
    assert cards[sealed]["offer_count"] is None and cards[visible]["offer_count"] == 1
    assert b.get(f"/projects/{sealed}").json()["offer_count"] is None and b.get(f"/projects/{visible}").json()["offer_count"] == 1
    # The owner still knows how many are in.
    assert owner.get(f"/projects/{sealed}").json()["offer_count"] == 1


def test_dashboard_counts_cover_every_offer_not_one_page(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pids = [_tender(owner, f"R{i}") for i in range(3)]
    for pid in pids:
        _submit(sp, pid)
    sp.post(f"/projects/{pids[0]}/offers/withdraw")
    assert len(sp.get("/service-provider/my-bids", params={"limit": 1}).json()) == 1
    assert sp.get("/service-provider/my-bids/summary").json() == {"total": 3, "active": 2, "won": 0}
    assert _account(db, "service_provider", "other@example.com").get("/service-provider/my-bids/summary").json() == {"total": 0, "active": 0, "won": 0}


def test_the_lock_judges_by_the_database_clock(db):
    owner = _account(db, "owner", "owner@example.com")
    pid = _tender(owner, "Clock")
    locked = lock_project(db, pid)
    assert abs((locked._judged_at - db_now(db)).total_seconds()) < 5
    # Decided by that time, not by whatever the app server's clock says later.
    locked.bid_deadline = locked._judged_at + timedelta(seconds=1)
    assert bidding_is_open(locked) is True
    locked._judged_at = locked.bid_deadline
    assert bidding_is_open(locked) is False
    db.rollback()

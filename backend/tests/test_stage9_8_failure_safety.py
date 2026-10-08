"""Stage 9.8: when something goes wrong part-way, the database tells the
truth -- a publication or an award either happens whole or not at all, a
stored file is never referenced unless it was stored, a retried offer is
still one offer, a refused request changes nothing -- and a notification that
can't be written after a committed change no longer turns that success into
an error (while one that fails with changes still pending still fails)."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement
from app.models.award_record import AwardRecord
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.offer import Offer, OfferDocument
from app.models.project import Project
from app.services import notify as notify_service
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import DECL, _d, _submitted, _tender


def _quiet(client):
    """The same signed-in session, answering 500 instead of raising in the test."""
    c = TestClient(app, raise_server_exceptions=False)
    c.cookies.update(client.cookies)
    return c


def test_failures_leave_the_truth(db, monkeypatch):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "a@example.com")
    b = _account(db, "service_provider", "b@example.com")
    other = _account(db, "owner", "other@example.com")

    # A. Publication fails at its last step (the audit write): no requirement goes live.
    draft = owner.post("/projects", data={"title": "Tower works", "address": "Kaifan", "description": "Repaint the tower.",
                                          "bid_deadline": (datetime.utcnow() + timedelta(days=9)).isoformat(), "status": "draft"}).json()["id"]
    import app.services.audit as audit

    with monkeypatch.context() as m:
        m.setattr(audit, "log_action", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("database gone")))
        assert _quiet(owner).post(f"/owner/projects/{draft}/publish").status_code == 500
    db.expire_all()
    p = db.get(Project, draft)
    assert (p.status.value, p.published_at) == ("draft", None)

    # B. Offers; the same submission sent twice is still one offer.
    pid = _tender(owner, title="Main job")
    _submitted(a, pid)
    assert a.post(f"/projects/{pid}/offers/draft/submit").status_code >= 400
    _submitted(b, pid)
    assert db.query(Offer).filter(Offer.project_id == pid, Offer.service_provider_id == a.get("/auth/me").json()["id"]).count() == 1

    # G. A file that can't be stored is never referenced.
    import app.routers.offers as offers_router

    class Broken:
        def save(self, *a, **k):
            raise OSError("disk full")

    p2 = _tender(owner, title="Files job")
    a.post(f"/projects/{p2}/participate")
    a.put(f"/projects/{p2}/offers/draft", json={"amount": "500", "accepted_declarations": [DECL], "proposed_start_date": _d(20), "proposed_duration_days": 10})
    with monkeypatch.context() as m:
        m.setattr(offers_router, "get_storage", lambda: Broken())
        assert _quiet(a).post(f"/projects/{p2}/offers/documents", data={"label": "Method statement"},
                              files={"file": ("m.pdf", b"%PDF-x", "application/pdf")}).status_code == 500
    assert db.query(OfferDocument).filter(OfferDocument.project_id == p2).count() == 0

    # D. The award fails at its last step: no award, no agreement, no offer marked won, still awardable.
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner.get("/owner/projects")
    win = a.get(f"/projects/{pid}/offers/mine").json()["id"]
    import app.routers.owner as owner_router

    with monkeypatch.context() as m:
        m.setattr(owner_router, "log_action", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("database gone")))
        assert _quiet(owner).post(f"/owner/projects/{pid}/offers/{win}/approve").status_code == 500
    db.expire_all()
    assert db.query(AwardRecord).filter(AwardRecord.project_id == pid).count() == 0
    assert db.query(Agreement).filter(Agreement.project_id == pid).count() == 0
    assert db.get(Offer, win).status.value == "submitted" and db.get(Project, pid).status.value != "awarded"

    # I. Another owner can't award it -- and nothing changes.
    assert other.post(f"/owner/projects/{pid}/offers/{win}/approve").status_code == 404
    assert db.query(AwardRecord).filter(AwardRecord.project_id == pid).count() == 0

    # E. Notices can't be written: the award (committed first) still succeeds and says so.
    from app.models.user import User

    p3 = _tender(owner, title="Third job")
    _submitted(b, p3)
    broken = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("notifications table down"))  # noqa: E731
    with monkeypatch.context() as m:
        m.setattr(notify_service, "_write", broken)
        assert owner.post(f"/owner/projects/{pid}/offers/{win}/approve").status_code == 200
        assert db.query(AwardRecord).filter(AwardRecord.project_id == pid).one().offer_id == win
        assert db.query(Notification).filter(Notification.type == NotificationType.award_won).count() == 0
        # ...and an offer withdrawal likewise.
        assert b.post(f"/projects/{p3}/offers/withdraw").status_code == 200
        db.expire_all()
        assert db.query(Offer).filter(Offer.project_id == p3).one().status.value == "withdrawn"
        # But with business changes still pending, a failing notice still fails -- nothing is lost silently.
        pending = db.get(Project, p3)
        pending.title = "Changed but not saved"
        with pytest.raises(RuntimeError):
            notify_service.notify(db, db.get(User, pending.owner_id), NotificationType.tender_closed, link="/x", project_title="x")
        db.rollback()
    assert db.get(Project, p3).title == "Third job"

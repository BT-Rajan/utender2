"""Stage 7.1: award handover. After the award, the owner and the winning
provider read one consistent record -- which requirement, which offer, which
provider, what value, when, on which version -- from the award record and the
authoritative states; losers and outsiders get nothing of it; the whole
pre-award history is still there; nothing reopens the requirement."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import NotificationType, OfferStatus, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer, OfferRevision
from app.models.offer_shortlist import OfferShortlist
from app.models.evaluation_note import EvaluationNote
from app.models.project import Project
from app.models.project_amendment import ProjectAmendment
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import REV2, _submitted, _tender


def _relogin(email):
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _awarded(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b, c = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr", "dana"))
    pid = _tender(owner)
    for sp in (a, b, c):
        _submitted(sp, pid)
    assert b.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}).status_code == 200  # B revised
    assert c.post(f"/projects/{pid}/offers/withdraw").status_code == 200  # C withdrew
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    ids = {n: db.query(Offer).filter(Offer.project_id == pid, Offer.service_provider_id == sp.get("/auth/me").json()["id"]).one().id for n, sp in (("amal", a), ("badr", b), ("dana", c))}
    owner.put(f"/owner/projects/{pid}/offers/{ids['badr']}/shortlist")
    owner.post(f"/owner/projects/{pid}/notes", json={"body": "Best programme.", "offer_id": ids["badr"]})
    assert owner.post(f"/owner/projects/{pid}/offers/{ids['badr']}/approve").status_code == 200
    return owner, a, b, c, pid, ids


def test_owner_and_winner_read_one_consistent_award(db):
    owner, a, b, c, pid, ids = _awarded(db)
    # The owner -- even after a fresh login.
    for client in (owner, _relogin("owner@example.com")):
        award = client.get(f"/projects/{pid}/award").json()
        assert (award["offer_id"], award["service_provider_company_name"], award["amount"], award["offer_revision"], award["material_revision"]) == (ids["badr"], "badr", "900.000", 2, 0)
        assert award["created_at"].endswith("Z")  # an instant, UTC
        assert client.get(f"/projects/{pid}").json()["status"] == "awarded"
        statuses = {o["id"]: o["status"] for o in client.get(f"/owner/projects/{pid}/offers").json()}
        assert statuses == {ids["badr"]: "approved", ids["amal"]: "rejected", ids["dana"]: "withdrawn"}
        assert client.get(f"/owner/projects/{pid}/offers/{ids['badr']}").json()["offer"]["status"] == "approved"
    # The winner: their offer awarded, at their price, when -- through the notification's own link.
    winner = _relogin("badr@example.com")
    award = winner.get(f"/projects/{pid}/award").json()
    assert (award["mine"], award["amount"], award["offer_id"], award["material_revision"]) == (True, "900.000", ids["badr"], 0)
    assert winner.get(f"/projects/{pid}/offers/mine").json()["status"] == "approved"
    assert {x["project_id"]: x["offer_status"] for x in winner.get("/service-provider/my-bids").json()}[pid] == "approved"
    uid = winner.get("/auth/me").json()["id"]
    (note,) = db.query(Notification).filter(Notification.user_id == uid, Notification.type == NotificationType.award_won).all()
    assert note.link == f"/service-provider/projects/{pid}/offer"
    assert winner.get(f"/projects/{pid}").status_code == 200  # the page behind that link opens


def test_others_never_read_the_winners_award(db):
    owner, a, b, c, pid, ids = _awarded(db)
    outsider = _account(db, "service_provider", "outsider@example.com")
    other_owner = _account(db, "owner", "other@example.com")
    loser = a.get(f"/projects/{pid}/award").json()
    assert (loser["mine"], loser["amount"], loser["offer_id"], loser["service_provider_company_name"], loser["material_revision"]) == (False, None, None, None, None)
    assert a.get(f"/projects/{pid}/offers/mine").json()["status"] == "rejected"  # never looks like a winner
    for client in (outsider, other_owner):
        assert client.get(f"/projects/{pid}/award").status_code == 404
        assert client.get(f"/owner/projects/{pid}/offers/{ids['badr']}").status_code in (403, 404)
    assert TestClient(app).get(f"/projects/{pid}/award").status_code == 401


def test_the_history_carries_on_and_nothing_reopens_it(db):
    owner, a, b, c, pid, ids = _awarded(db)
    # Pre-award history intact: revisions, the withdrawn offer, shortlist, notes.
    assert [r.revision_number for r in db.query(OfferRevision).filter(OfferRevision.offer_id == ids["badr"])] == [1]
    assert db.get(Offer, ids["dana"]).status == OfferStatus.withdrawn
    assert db.query(OfferShortlist).filter(OfferShortlist.offer_id == ids["badr"]).count() == 1
    assert db.query(EvaluationNote).filter(EvaluationNote.offer_id == ids["badr"]).count() == 1
    assert owner.get(f"/owner/projects/{pid}/offers/{ids['badr']}/history").json()[0]["amount"] == "1000.000"
    assert db.query(ProjectAmendment).filter(ProjectAmendment.project_id == pid).count() == 0
    # Nothing reopens it: no offers, no award, no other ending, no amendment, the deadline passing.
    assert a.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}).status_code == 400
    assert owner.post(f"/owner/projects/{pid}/offers/{ids['amal']}/approve").status_code == 400
    assert owner.post(f"/owner/projects/{pid}/offers/{ids['badr']}/approve").status_code == 400  # a retry
    for action, body in (("no-award", {}), ("cancel", {"reason": "other"}), ("close", None), ("start-evaluation", None)):
        assert owner.post(f"/owner/projects/{pid}/{action}", json=body).status_code == 400, action
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"title": "Reopened?"}, headers={"If-Match": str(v)}).status_code in (400, 409)
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.get("/owner/projects")  # the expiry sweep
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded
    assert {o.id: o.status for o in db.query(Offer)} == {ids["badr"]: OfferStatus.approved, ids["amal"]: OfferStatus.rejected, ids["dana"]: OfferStatus.withdrawn}

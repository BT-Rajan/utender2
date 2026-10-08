"""Stage 7.2: the post-award transaction record. The award record is the one
record of "owner X awarded requirement Y to provider Z on offer W": created
with the award, one per requirement, readable in full by the owner side and
the winner (each seeing the counterparty), by no one else; nothing leaves it
partial or orphaned."""
from fastapi.testclient import TestClient

from app.main import app
from app.models.award_record import AwardRecord
from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _submitted, _tender


def _awarded(db, organization=None):
    owner = _account(db, "owner", "owner@example.com", organization=organization)
    win, lose = (_account(db, "service_provider", f"{n}@example.com") for n in ("badr", "amal"))
    pid = _tender(owner)
    _submitted(win, pid)
    _submitted(lose, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    wid = win.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    return owner, win, lose, pid, wid


def test_one_record_links_owner_requirement_offer_and_provider(db):
    owner, win, lose, pid, wid = _awarded(db, organization="Gulf Holdings W.L.L.")
    (record,) = db.query(AwardRecord).all()
    offer = db.get(Offer, wid)
    project = db.get(Project, pid)
    assert (record.project_id, record.offer_id, record.service_provider_id, record.amount) == (pid, wid, offer.service_provider_id, offer.amount)
    assert record.awarded_by == owner.get("/auth/me").json()["id"] and record.project_revision == project.revision

    for client in (owner, win):  # each side reads the same record, with its counterparty
        a = client.get(f"/projects/{pid}/award").json()
        assert (a["id"], a["project_id"], a["offer_id"], a["amount"]) == (record.id, pid, wid, "1000.000")
        assert (a["owner_name"], a["service_provider_company_name"]) == ("Gulf Holdings W.L.L.", "badr")
        assert a["created_at"].endswith("Z")
        assert client.get(f"/projects/{pid}").json()["status"] == "awarded"  # the post-award status
    assert win.get(f"/projects/{pid}/award").json()["mine"] is True
    assert {x["project_id"]: x["offer_status"] for x in win.get("/service-provider/my-bids").json()}[pid] == "approved"


def test_an_individual_owner_is_named_by_their_own_name(db):
    owner, win, lose, pid, wid = _awarded(db)
    assert win.get(f"/projects/{pid}/award").json()["owner_name"] == "N"


def test_isolation_losers_outsiders_and_other_owners(db):
    owner, win, lose, pid, wid = _awarded(db, organization="Gulf Holdings W.L.L.")
    a = lose.get(f"/projects/{pid}/award").json()
    for key in ("id", "offer_id", "service_provider_id", "amount", "owner_name", "service_provider_company_name", "awarded_by"):
        assert a[key] is None, key
    assert a["mine"] is False
    for client in (_account(db, "service_provider", "outsider@example.com"), _account(db, "owner", "other@example.com")):
        assert client.get(f"/projects/{pid}/award").status_code == 404
    assert TestClient(app).get(f"/projects/{pid}/award").status_code == 401
    assert _admin(db).get(f"/projects/{pid}/award").json()["id"] == db.query(AwardRecord).one().id


def test_no_second_partial_or_orphaned_record(db):
    owner, win, lose, pid, wid = _awarded(db)
    lid = lose.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 400  # a retry
    assert owner.post(f"/owner/projects/{pid}/offers/{lid}/approve").status_code == 400
    assert db.query(AwardRecord).count() == 1
    # Nothing deletes what the record points at.
    admin = _admin(db)
    assert admin.delete(f"/admin/offers/{wid}").status_code == 400
    sp_id = win.get("/auth/me").json()["id"]
    assert admin.delete(f"/admin/service-providers/{sp_id}").status_code == 400
    db.expire_all()
    record = db.query(AwardRecord).one()
    assert db.get(Offer, record.offer_id) is not None and db.get(Project, record.project_id) is not None


def test_a_requirement_without_an_award_has_no_record(db):
    owner = _account(db, "owner", "owner@example.com")
    pid = _tender(owner)
    assert owner.get(f"/projects/{pid}/award").status_code == 404
    assert db.query(AwardRecord).count() == 0

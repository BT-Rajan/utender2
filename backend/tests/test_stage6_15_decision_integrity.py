"""Stage 6.15: decision integrity & concurrency. One authoritative outcome per
requirement: simultaneous award / no-award / cancel / end-outside requests,
repeats and stale tabs settle on exactly one (MySQL: real row locks); a
decided or ended requirement's offers stay exactly as they were."""
from concurrent.futures import ThreadPoolExecutor

from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import OfferStatus, ProjectStatus
from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage3_bid_integrity import _bid, _login, _owner, _project, _service_provider, needs_mysql
from tests.test_stage4_9_participation import _admin

DECISIONS = {
    "award-1": ("offers/{o1}/approve", None),
    "award-2": ("offers/{o2}/approve", None),
    "no-award": ("no-award", {}),
    "cancel": ("cancel", {"reason": "not_needed"}),
    "close-externally": ("close-externally", {}),
}


DECISION_ACTIONS = {"project.award", "project.no_award", "project.cancel", "project.closed_externally"}


def _closed_with_two_offers(db, n=0):
    owner, _ = _owner(db, f"owner{n or ''}@example.com")
    c1, _ = _service_provider(db, f"c1-{n}@example.com")
    c2, _ = _service_provider(db, f"c2-{n}@example.com", "BuildCo")
    pid = _project(owner)
    o1 = _bid(c1, pid, "1000.00").json()["id"]
    o2 = _bid(c2, pid, "1100.00").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    return owner, pid, o1, o2


def _consistent(db, pid):
    """The requirement's state, its offers and its award record agree."""
    db.expire_all()
    project = db.get(Project, pid)
    statuses = sorted(o.status.value for o in db.query(Offer).filter_by(project_id=pid))
    awards = db.query(AwardRecord).filter_by(project_id=pid).all()
    if project.status == ProjectStatus.awarded:
        assert len(awards) == 1 and statuses == ["approved", "rejected"]
        assert db.get(Offer, awards[0].offer_id).status == OfferStatus.approved
    else:
        assert project.status in (ProjectStatus.no_award, ProjectStatus.canceled) and awards == [] and statuses == ["submitted", "submitted"]
    return project


@needs_mysql
def test_every_pair_of_simultaneous_final_decisions_settles_on_exactly_one(db):
    for n, (first, second) in enumerate((("award-1", "no-award"), ("award-1", "cancel"), ("award-2", "close-externally"), ("no-award", "cancel")), start=1):
        owner, pid, o1, o2 = _closed_with_two_offers(db, n)
        tabs = [_login(f"owner{n}@example.com"), _login(f"owner{n}@example.com")]

        def decide(args):
            client, name = args
            path, body = DECISIONS[name]
            return client.post(f"/owner/projects/{pid}/{path.format(o1=o1, o2=o2)}", json=body)

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(decide, zip(tabs, (first, second))))
        assert sorted(r.status_code for r in results) == [200, 400], (first, second, [(r.status_code, r.text[:80]) for r in results])
        _consistent(db, pid)
        # The audit log has the one decision that stood.
        decided = [e.action for e in db.query(AuditLog).filter(AuditLog.target_id == pid) if e.action in DECISION_ACTIONS]
        assert len(decided) == 1, (first, second, decided)


@needs_mysql
def test_a_double_clicked_award_is_one_award(db):
    owner, pid, o1, _ = _closed_with_two_offers(db)
    tabs = [_login("owner@example.com") for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        codes = sorted(r.status_code for r in pool.map(lambda c: c.post(f"/owner/projects/{pid}/offers/{o1}/approve"), tabs))
    assert codes == [200, 400, 400, 400], codes
    _consistent(db, pid)
    assert db.query(AuditLog).filter(AuditLog.target_id == pid, AuditLog.action == "project.award").count() == 1


def test_retries_and_stale_tabs_never_change_a_decided_outcome(db):
    owner, pid, o1, o2 = _closed_with_two_offers(db)
    assert owner.post(f"/owner/projects/{pid}/offers/{o1}/approve").status_code == 200
    # A network retry, then a tab opened before the award trying everything else.
    for name in DECISIONS:
        path, body = DECISIONS[name]
        assert owner.post(f"/owner/projects/{pid}/{path.format(o1=o1, o2=o2)}", json=body).status_code == 400, name
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 400
    assert owner.post(f"/owner/projects/{pid}/start-evaluation").status_code == 400
    project = _consistent(db, pid)
    assert project.status == ProjectStatus.awarded
    (record,) = db.query(AwardRecord).filter_by(project_id=pid).all()
    assert record.offer_id == o1 and db.query(AuditLog).filter(AuditLog.target_id == pid, AuditLog.action == "project.award").count() == 1


def test_an_ended_requirements_offers_stay_as_they_were_even_for_an_admin(db):
    admin = _admin(db)
    owner, _ = _owner(db)
    c1, _ = _service_provider(db, "c1@example.com")
    for end, body in (("cancel", {"reason": "not_needed"}), ("close-externally", {}), ("no-award", {})):
        pid = _project(owner)
        oid = _bid(c1, pid, "1000.00").json()["id"]
        if end == "no-award":
            owner.post(f"/owner/projects/{pid}/close")
        assert owner.post(f"/owner/projects/{pid}/{end}", json=body).status_code == 200
        r = admin.patch(f"/admin/offers/{oid}", json={"amount": "1.000"})
        assert r.status_code == 400, (end, r.text)
        db.expire_all()
        assert str(db.get(Offer, oid).amount) == "1000.000"
    # Expired at the deadline (its only offer withdrawn): the same.
    pid = _project(owner)
    oid = _bid(c1, pid, "1000.00").json()["id"]
    assert c1.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    from datetime import datetime, timedelta
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.get("/owner/projects")  # the expiry sweep
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.expired
    assert admin.patch(f"/admin/offers/{oid}", json={"amount": "1.000"}).status_code == 400

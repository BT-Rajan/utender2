"""Stage 7.15: post-award integrity under concurrent actions. Every
post-award change is decided under the requirement's row lock and checked
against the rows it governs; those checks must see what the lock's previous
holder committed. The application's MySQL connections therefore run at READ
COMMITTED -- at the default REPEATABLE READ a request that read anything
before waiting for the lock judged later rows from its earlier snapshot.
Plus the lifecycle races not covered by the earlier stages' own race tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.models.agreement import Agreement, ExecutionUpdate, Variation
from app.models.enums import ProjectStatus
from app.models.project import Project
from app.models.user import User
from app.services.tender_lifecycle import lock_project
from tests.conftest import TEST_DATABASE_URL
from tests.stage7_helpers import put_in_force
from tests.test_stage3_bid_integrity import needs_mysql
from tests.test_stage7_10_completion import _a, _do, _relogin, _started, _v


def test_mysql_connections_read_committed_data():
    assert db_module.engine_options("mysql+pymysql://u:p@h/db")["isolation_level"] == "READ COMMITTED"
    assert "isolation_level" not in db_module.engine_options("sqlite:///:memory:")


@needs_mysql
def test_a_request_waiting_on_the_lock_judges_what_the_holder_committed(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    # A request built exactly as production builds it, which has already read
    # something (its user) before reaching the lock...
    engine = sa.create_engine(TEST_DATABASE_URL, **db_module.engine_options(TEST_DATABASE_URL))
    late = sessionmaker(bind=engine, autoflush=False)()
    try:
        late.query(User).first()
        late.query(Agreement).filter(Agreement.project_id == pid).one()  # and seen the agreement as "submitted"
        # ...while another owner accepts and commits.
        assert _do(owner, pid, "accept").status_code == 200
        lock_project(late, pid)
        seen = late.query(Agreement).filter(Agreement.project_id == pid).one()
        late.refresh(seen)
        assert (seen.completion_status, seen.status) == ("accepted", "completed")  # not the stale "submitted"
    finally:
        late.rollback()
        late.close()
        engine.dispose()


@needs_mysql
def test_completion_racing_termination_settles_on_one_outcome(db):
    for n in range(3):
        if n:
            db.expire_all()
        owner, a, b, pid, wid, _ = _started(db) if n == 0 else _fresh(db, n)
        # Batch A: submitted work can't be terminated (the owner accepts or returns it
        # first), so the race that can still happen is the submission against the termination.
        calls = [lambda: _relogin(provider_email(n)).post(f"/projects/{pid}/agreement/completion/submit", json={}),
                 lambda: _relogin(owner_email(n)).post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stop."})]
        with ThreadPoolExecutor(2) as pool:
            codes = [f.result().status_code for f in [pool.submit(c) for c in calls]]
        db.expire_all()
        ag = db.query(Agreement).filter(Agreement.project_id == pid).one()
        # Exactly one outcome, whichever request took the lock first: submitted for
        # review (the termination refused), or terminated (the submission refused).
        assert codes.count(200) == 1, (codes, ag.status, ag.completion_status)
        assert (ag.status, ag.completion_status) in (("active", "submitted"), ("terminated", None)), (ag.status, ag.completion_status)
        assert (ag.status == "terminated") == (ag.terminated_at is not None) == (ag.completion_submitted_at is None)
        assert ag.completed_at is None
        ends = [u.kind for u in db.query(ExecutionUpdate).filter(ExecutionUpdate.agreement_id == ag.id, ExecutionUpdate.kind.in_(("completed", "terminated")))]
        assert ends == (["terminated"] if ag.status == "terminated" else [])  # the history records only what happened


def owner_email(n):
    return "owner@example.com" if n == 0 else f"owner{n}@example.com"


def provider_email(n):
    return "amal@example.com" if n == 0 else f"amal{n}@example.com"


def _fresh(db, n):
    from tests.test_stage4_9_participation import _account
    from tests.test_stage5_13_revise import _submitted, _tender

    owner = _account(db, "owner", owner_email(n))
    a = _account(db, "service_provider", f"amal{n}@example.com")
    pid = _tender(owner, title=f"Job {n}")
    _submitted(a, pid)
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{a.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    put_in_force(owner, a, pid)  # Batch A: effective today (Kuwait), provider confirms, owner activates
    a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid))
    return owner, a, None, pid, None, []


@needs_mysql
def test_a_change_proposal_racing_the_completion_submission_never_both_stand(db):
    owner, a, b, pid, wid, _ = _started(db)
    calls = [lambda: _relogin("owner@example.com").post(f"/projects/{pid}/agreement/variations", json={"description": "Extra.", "value_change": "100"}),
             lambda: _relogin("amal@example.com").post(f"/projects/{pid}/agreement/completion/submit", json={})]
    with ThreadPoolExecutor(2) as pool:
        codes = [f.result().status_code for f in [pool.submit(c) for c in calls]]
    db.expire_all()
    ag = db.query(Agreement).one()
    open_changes = db.query(Variation).filter(Variation.status == "proposed").count()
    assert codes.count(200) == 1, codes
    assert not (open_changes and ag.completion_status == "submitted")  # never work under review with a change pending


def test_background_expiry_never_touches_post_award_records(db):
    owner, a, b, pid, wid, _ = _started(db)
    _do(a, pid, "submit")
    _do(owner, pid, "accept")
    project = db.get(Project, pid)
    project.bid_deadline = datetime.utcnow() - timedelta(days=30)
    db.commit()
    owner.get("/owner/projects")  # the lazy expiry sweep
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded
    assert _a(owner, pid)["status"] == "completed"

"""Stage 5.1: a provider who decides to take part starts exactly one offer
workspace for that requirement and stakeholder -- at the requirement's
current version, judged by the server under the requirement's lock -- and
never one for a requirement that isn't open to them."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import ProjectStatus
from app.models.participation import Participation
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.services.team import org_of
from tests.test_stage4_9_participation import _account, _admin, _publish, _when


def _member(db, boss, email):
    c = _account(db, "service_provider", email, joining=True)
    token = boss.post("/account/organization/invitations", json={"email": email}).json()["link"].rsplit("/", 1)[-1]
    c.post(f"/account/invitations/{token}/accept")
    return c


def test_start_creates_one_offer_draft_bound_to_requirement_version_and_stakeholder(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    v = owner.get(f"/projects/{pid}").json()["version"]
    owner.patch(f"/projects/{pid}", json={"description": "Rewire a villa: 40 points plus 6 outdoor."}, headers={"If-Match": str(v)})
    me = sp.get("/auth/me").json()["id"]
    # Double-click, a second tab, a retry: one draft.
    for _ in range(3):
        r = sp.post(f"/projects/{pid}/participate")
        assert r.status_code == 200 and r.json()["started"] is True
    record = db.query(Participation).one()
    assert (record.project_id, record.service_provider_id, record.organization_id, record.started_by) == (pid, me, None, me)
    # Started against the requirement as it stands now (after the amendment), not as first published.
    assert record.seen_material_revision == db.get(Project, pid).material_revision == 1
    # Submitting later uses the same draft, not a second one.
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "900"}).status_code == 200
    assert db.query(Participation).count() == 1


def test_an_organization_has_one_draft_whoever_starts_it(db):
    owner = _account(db, "owner", "owner@example.com")
    boss = _account(db, "service_provider", "boss@gulf.example", organization="Gulf Electrical")
    eng = _member(db, boss, "eng@gulf.example")
    ops = _member(db, boss, "ops@gulf.example")
    pid = _publish(owner)
    for c in (eng, ops, boss, eng):
        assert c.post(f"/projects/{pid}/participate").status_code == 200
    record = db.query(Participation).one()
    boss_id = boss.get("/auth/me").json()["id"]
    assert record.service_provider_id == boss_id and record.organization_id == org_of(db, boss_id)
    assert record.started_by == eng.get("/auth/me").json()["id"]
    # The database itself refuses a second draft for the same organization,
    # even under a different acting profile.
    other = db.query(ServiceProviderProfile).filter(ServiceProviderProfile.user_id != boss_id).first()
    db.add(Participation(project_id=pid, service_provider_id=other.user_id, organization_id=record.organization_id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_no_draft_for_a_requirement_not_open_to_them(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    admin = _admin(db)
    expired, canceled, suspended = (_publish(owner, t) for t in ("Expired", "Canceled", "Suspended"))
    db.get(Project, expired).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    owner.post(f"/owner/projects/{canceled}/cancel", json={"reason": "not_needed"})
    admin.post(f"/admin/projects/{suspended}/suspend", json={"suspended": True})
    draft = owner.post("/projects", data={"title": "Draft", "address": "x", "bid_deadline": _when(9)}).json()["id"]

    r = sp.post(f"/projects/{expired}/participate")
    assert r.status_code == 400 and r.json()["detail"] == "This requirement is no longer accepting offers. Its response deadline has passed."
    ar = sp.post(f"/projects/{expired}/participate", headers={"Accept-Language": "ar"})
    assert "انتهى موعد تقديم العروض" in ar.json()["detail"]
    r = sp.post(f"/projects/{canceled}/participate")
    assert r.status_code == 400 and r.json()["detail"] == "This requirement is no longer accepting offers."  # ended by the owner, not the deadline
    r = sp.post(f"/projects/{suspended}/participate")
    assert r.status_code == 400 and "deadline" not in r.json()["detail"]  # reveals nothing beyond unavailable
    assert sp.post(f"/projects/{draft}/participate").status_code == 404
    assert sp.post("/projects/00000000-0000-0000-0000-000000000000/participate").status_code == 404
    assert db.query(Participation).count() == 0


def test_closed_early_is_not_reported_as_the_deadline(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    project = db.get(Project, pid)
    project.status, project.closed_at = ProjectStatus.closed, datetime.utcnow() - timedelta(days=1)
    project.bid_deadline = datetime.utcnow() - timedelta(hours=1)  # deadline passed after offers had already stopped
    db.commit()
    assert sp.post(f"/projects/{pid}/participate").json()["detail"] == "This requirement is no longer accepting offers."

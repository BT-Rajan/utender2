"""An organization is never left without a working representative: an admin
can't deactivate the person who keeps it manageable, a representative can't
walk out from under colleagues, and an admin can add a person or appoint a
member to put one back."""
from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import MembershipRole
from app.models.organization import OrganizationMembership
from app.models.user import User
from tests._verified import verify_email
from tests.test_organization_sharing import _account, _organization
from tests.test_stage8_15_review_moderation import _admin
from datetime import datetime


def _org_id(db, user_id):
    db.expire_all()
    return db.query(OrganizationMembership).filter(OrganizationMembership.user_id == user_id).one().organization_id


def _roles(db, org_id):
    db.expire_all()
    rows = db.query(OrganizationMembership, User).join(User, User.id == OrganizationMembership.user_id).filter(OrganizationMembership.organization_id == org_id).all()
    return {u.email: m.role.value for m, u in rows}


def _setup(db):
    admin = _admin(db)
    boss, member, boss_id, member_id = _organization(db, "service_provider", "Gulf Electrical", "boss@gulf.example", "eng@gulf.example")
    return admin, boss, member, boss_id, member_id, _org_id(db, boss_id)


def test_admin_cannot_deactivate_the_representative_but_can_a_member(db):
    admin, boss, member, boss_id, member_id, org = _setup(db)
    r = admin.post(f"/admin/users/{boss_id}/deactivate", json={})
    assert r.status_code == 409 and "representative" in r.json()["detail"]
    db.expire_all()
    assert db.get(User, boss_id).deactivated_at is None
    assert admin.post(f"/admin/users/{member_id}/deactivate", json={}).status_code == 200  # an ordinary member is fine


def test_appointing_another_representative_unblocks_deactivation(db):
    admin, boss, member, boss_id, member_id, org = _setup(db)
    r = admin.post(f"/admin/organizations/{org}/representative", json={"user_id": member_id, "reason": "boss left the company"})
    assert r.status_code == 200
    assert _roles(db, org) == {"boss@gulf.example": "member", "eng@gulf.example": "admin"}
    assert admin.post(f"/admin/users/{boss_id}/deactivate", json={}).status_code == 200
    # the new representative manages the organization
    assert member.post("/account/organization/invitations", json={"email": "new@gulf.example"}).status_code == 201
    row = db.query(AuditLog).filter(AuditLog.action == "organization.representative_changed").one()
    assert (row.previous_value, row.new_value, row.reason, row.actor_id != boss_id) == (boss_id, member_id, "boss left the company", True)


def test_appointment_guards(db):
    admin, boss, member, boss_id, member_id, org = _setup(db)
    assert admin.post(f"/admin/organizations/{org}/representative", json={"user_id": boss_id}).status_code == 400  # already
    assert admin.post(f"/admin/organizations/{org}/representative", json={"user_id": "nobody"}).status_code == 404
    assert admin.post("/admin/organizations/nope/representative", json={"user_id": member_id}).status_code == 404
    assert boss.post(f"/admin/organizations/{org}/representative", json={"user_id": member_id}).status_code == 403  # not an admin
    db.expire_all()
    db.get(User, member_id).deactivated_at = datetime.utcnow()
    db.commit()
    assert admin.post(f"/admin/organizations/{org}/representative", json={"user_id": member_id}).status_code == 409  # deactivated
    assert _roles(db, org)["boss@gulf.example"] == "admin"


def test_admin_adds_a_person_as_the_representative_of_a_stranded_organization(db):
    admin, boss, member, boss_id, member_id, org = _setup(db)
    # the state the old code allowed: representative and colleague both deactivated
    db.expire_all()
    for uid in (boss_id, member_id):
        db.get(User, uid).deactivated_at = datetime.utcnow()
    db.commit()
    _account("service_provider", "newlead@gulf.example")
    verify_email("newlead@gulf.example")
    r = admin.post(f"/admin/organizations/{org}/members", json={"email": "NewLead@gulf.example", "representative": True, "position": "Director", "reason": "restoring access"})
    assert r.status_code == 201 and r.json()["role"] == "admin"
    assert _roles(db, org) == {"boss@gulf.example": "member", "eng@gulf.example": "member", "newlead@gulf.example": "admin"}
    actions = sorted(a.action for a in db.query(AuditLog).filter(AuditLog.target_id == org).all())
    assert "organization.member_added_by_admin" in actions and "organization.representative_changed" in actions


def test_admin_adds_an_ordinary_member_and_the_guards(db):
    admin, boss, member, boss_id, member_id, org = _setup(db)
    add = lambda **b: admin.post(f"/admin/organizations/{org}/members", json={"email": "x@gulf.example", **b})
    assert add().status_code == 404  # no account yet
    # signed up directly: the shared helper marks every account verified
    assert TestClient(app).post("/auth/signup", json={"email": "x@gulf.example", "password": "password123", "full_name": "X", "role": "service_provider"}).status_code == 201
    assert add().status_code == 409  # email not verified
    verify_email("x@gulf.example")
    assert add().status_code == 201 and _roles(db, org)["x@gulf.example"] == "member"
    assert _roles(db, org)["boss@gulf.example"] == "admin"  # the representative is unchanged
    assert add().status_code == 409  # already belongs to an organization
    _account("owner", "own@gulf.example")  # verified by the helper
    assert admin.post(f"/admin/organizations/{org}/members", json={"email": "own@gulf.example"}).status_code == 400  # other side
    assert boss.post(f"/admin/organizations/{org}/members", json={"email": "x@gulf.example"}).status_code == 403


def test_last_active_person_cannot_be_deactivated_when_the_representative_already_is(db):
    admin, boss, member, boss_id, member_id, org = _setup(db)
    db.expire_all()
    db.get(User, boss_id).deactivated_at = datetime.utcnow()  # representative already gone
    db.commit()
    r = admin.post(f"/admin/users/{member_id}/deactivate", json={})
    assert r.status_code == 409
    db.expire_all()
    assert db.get(User, member_id).deactivated_at is None


def test_a_representative_cannot_leave_while_colleagues_remain(db):
    c = lambda e: _account("service_provider", e)
    boss, boss_id = c("boss@gulf.example")
    assert boss.put("/account/stakeholder", json={"type": "organization", "legal_name": "Gulf Electrical", "authorized": True}).status_code == 200
    colleague, _ = c("eng@gulf.example")
    verify_email("eng@gulf.example")
    token = boss.post("/account/organization/invitations", json={"email": "eng@gulf.example"}).json()["link"].rsplit("/", 1)[-1]
    assert colleague.post(f"/account/invitations/{token}/accept").status_code == 200
    r = boss.put("/account/stakeholder", json={"type": "individual"})
    assert r.status_code == 409 and "Other people still act" in r.json()["detail"]
    org = _org_id(db, boss_id)
    assert _roles(db, org)["boss@gulf.example"] == "admin"
    # once they are the only one left, setting up as an individual is unchanged
    assert boss.delete(f"/account/organization/members/{[m['user_id'] for m in boss.get('/account/organization/members').json() if m['role'] == 'member'][0]}").status_code in (200, 204)


def test_admin_detail_exposes_the_organization_id(db):
    admin, boss, member, boss_id, member_id, org = _setup(db)
    r = admin.get(f"/admin/service-providers/{boss_id}")
    assert r.status_code == 200 and r.json()["organization_id"] == org

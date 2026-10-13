"""Review fixes, accounts and sessions:
- an email change (self-service or by an admin) kills every verify/reset link
  issued before it, and a link only ever proves the address it was sent to;
- an email change ends the account's other sessions (the tab that made a
  self-service change carries on);
- a one-person organisation's representative can be deactivated;
- making someone the representative demotes every other admin membership;
- an IP-wide login lockout isn't pinned on whichever account tripped it;
- replaying a retired refresh token is audited once per window, not per request."""
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.enums import MembershipRole
from app.models.organization import OrganizationMembership
from app.models.user import User
from app.services.login_throttle import LoginThrottle
from tests.test_organization_sharing import _account as _verified_account, _organization
from tests.test_stage4_9_participation import _account, _admin


@pytest.fixture
def mail(monkeypatch):
    """Captures the links and codes that would have been emailed."""
    box = {"verify": [], "reset": [], "codes": []}
    import app.auth.router as auth_router
    import app.routers.admin as admin_module  # noqa: F401  (imports its senders lazily from app.services.email)
    import app.services.email as email_module
    import app.services.email_change as svc

    def verify(to, token):
        box["verify"].append((to, token))

    monkeypatch.setattr(auth_router, "notify_verify_email", verify)
    monkeypatch.setattr(auth_router, "notify_password_reset", lambda to, token: box["reset"].append((to, token)))
    monkeypatch.setattr(svc, "notify_verify_email", verify)
    monkeypatch.setattr(svc, "notify_email_changed", lambda old, new: None)
    monkeypatch.setattr(svc, "notify_email_change_code", lambda to, new, code: box["codes"].append(code))
    monkeypatch.setattr(email_module, "notify_verify_email", verify)
    monkeypatch.setattr(email_module, "notify_email_changed", lambda old, new: None)
    return box


def _signup(email, role="owner"):
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    assert r.status_code == 201, r.text
    return c, r.json()["id"]


def _login(email):
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _change_email(c, mail, new):
    assert c.post("/auth/email-change/request", json={"new_email": new, "current_password": "password123"}).status_code == 200
    r = c.post("/auth/email-change/confirm", json={"code": mail["codes"][-1]})
    assert r.status_code == 200, r.text
    return r


# ---------- 1. a verify link issued before an email change can't verify the new address ----------


def test_old_verify_link_cannot_verify_an_address_changed_to_later(db, mail):
    rep, _ = _verified_account("owner", "rep@corp.example")
    assert rep.put("/account/stakeholder", json={"type": "organization", "legal_name": "Corp W.L.L.", "authorized": True}).status_code == 200
    invite = rep.post("/account/organization/invitations", json={"email": "victim@corp.example"}).json()["link"].rsplit("/", 1)[-1]

    attacker, uid = _signup("attacker@evil.example")
    (_, old_link), = mail["verify"][-1:]
    _change_email(attacker, mail, "victim@corp.example")  # the code went to the attacker's own mailbox

    assert attacker.post("/auth/verify-email", json={"token": old_link}).status_code == 400
    db.expire_all()
    assert db.get(User, uid).email_verified is False
    assert attacker.post(f"/account/invitations/{invite}/accept").status_code == 403
    # The link sent to the new address does work.
    to, new_link = mail["verify"][-1]
    assert to == "victim@corp.example"
    assert attacker.post("/auth/verify-email", json={"token": new_link}).status_code == 200


def test_link_only_proves_the_address_it_was_sent_to(db, mail):
    """Even a link that somehow survived the change is bound to its address."""
    from app.models.auth_token import AuthToken

    c, uid = _signup("first@example.com")
    _, link = mail["verify"][-1]
    db.get(User, uid).email = "second@example.com"  # bypassing the services, which would kill the link
    db.commit()
    assert c.post("/auth/verify-email", json={"token": link}).status_code == 400
    assert db.query(AuthToken).filter(AuthToken.user_id == uid).first().email == "first@example.com"


# ---------- 2. an admin email change kills old links and every session ----------


def test_admin_email_change_kills_reset_links_and_sessions(db, mail):
    admin = _admin(db)
    c, uid = _signup("lost@example.com")
    other = _login("lost@example.com")
    assert TestClient(app).post("/auth/forgot-password", json={"email": "lost@example.com"}).status_code == 200
    _, reset = mail["reset"][-1]

    r = admin.patch(f"/admin/users/{uid}", json={"email": "found@example.com", "reason": "lost mailbox"})
    assert r.status_code == 200, r.text

    assert TestClient(app).post("/auth/reset-password", json={"token": reset, "new_password": "hijacked123"}).status_code == 400
    for session in (c, other):
        assert session.get("/auth/me").status_code == 401
        assert session.post("/auth/refresh").status_code == 401
    assert admin.get("/auth/me").status_code == 200  # the admin's own session is untouched
    assert _login("found@example.com").get("/auth/me").json()["email"] == "found@example.com"


def test_self_service_email_change_ends_other_sessions_but_not_this_one(db, mail):
    c, _ = _signup("me@example.com")
    other = _login("me@example.com")
    assert TestClient(app).post("/auth/forgot-password", json={"email": "me@example.com"}).status_code == 200
    _, reset = mail["reset"][-1]

    _change_email(c, mail, "me2@example.com")

    assert c.get("/auth/me").status_code == 200 and c.post("/auth/refresh").status_code == 200
    assert other.get("/auth/me").status_code == 401 and other.post("/auth/refresh").status_code == 401
    assert TestClient(app).post("/auth/reset-password", json={"token": reset, "new_password": "hijacked123"}).status_code == 400


# ---------- 7. a sole-member organisation can be deactivated ----------


def test_sole_member_organisation_can_be_deactivated(db):
    admin = _admin(db)
    _account(db, "owner", "solo@example.com", organization="Solo Co")
    solo = db.query(User).filter(User.email == "solo@example.com").one()
    assert db.query(OrganizationMembership).filter(OrganizationMembership.user_id == solo.id).one().role == MembershipRole.admin
    r = admin.post(f"/admin/users/{solo.id}/deactivate", json={"reason": "left"})
    assert r.status_code == 200, r.text

    # With a colleague, the representative is still what keeps it manageable.
    _, _, rep_id, _ = _organization(db, "owner", "Pair Co", "rep@pair.example", "mem@pair.example")
    assert admin.post(f"/admin/users/{rep_id}/deactivate", json={}).status_code == 409


# ---------- 8. exactly one representative, whatever state the rows were in ----------


def test_making_a_representative_demotes_every_other_admin(db):
    admin = _admin(db)
    _, _, rep_id, member_id = _organization(db, "owner", "Twin Co", "rep@twin.example", "mem@twin.example")
    org_id = db.query(OrganizationMembership).filter(OrganizationMembership.user_id == rep_id).one().organization_id
    # Two admins, as a lost race could have left them.
    db.query(OrganizationMembership).filter(OrganizationMembership.user_id == member_id).one().role = MembershipRole.admin
    db.commit()
    _verified_account("owner", "third@twin.example")

    r = admin.post(f"/admin/organizations/{org_id}/members", json={"email": "third@twin.example", "representative": True})
    assert r.status_code == 201, r.text
    db.expire_all()
    admins = db.query(OrganizationMembership).filter(
        OrganizationMembership.organization_id == org_id, OrganizationMembership.role == MembershipRole.admin
    ).all()
    assert [db.get(User, m.user_id).email for m in admins] == ["third@twin.example"]


# ---------- 13. the IP-wide lockout isn't audited against one account ----------


def test_throttle_reports_which_limit_locked():
    t = LoginThrottle(max_per_account=3, max_per_ip=4)
    assert [t.record_failure("1.1.1.1", "a@x") for _ in range(3)] == [None, None, "account"]
    assert t.record_failure("1.1.1.1", "b@x") == "ip"


def test_ip_lockout_goes_to_the_log_not_the_tripping_account(db, caplog):
    _, uid = _signup("real@example.com")
    for i in range(29):  # credential stuffing across addresses that have no account
        TestClient(app).post("/auth/login", json={"email": f"ghost{i}@example.com", "password": "nope-nope"})
    with caplog.at_level(logging.WARNING, logger="app.auth.router"):
        assert TestClient(app).post("/auth/login", json={"email": "real@example.com", "password": "nope-nope"}).status_code == 401
    actions = [a.action for a in db.query(AuditLog).filter(AuditLog.target_id == uid)]
    assert "login.locked" not in actions and actions.count("login.failed") == 1
    assert any("locked" in rec.getMessage() for rec in caplog.records)


def test_account_lockout_is_still_audited_once(db):
    _, uid = _signup("guessed@example.com")
    for _ in range(5):
        TestClient(app).post("/auth/login", json={"email": "guessed@example.com", "password": "nope-nope"})
    assert db.query(AuditLog).filter(AuditLog.target_id == uid, AuditLog.action == "login.locked").count() == 1


# ---------- 14. a replayed refresh token can't flood the trail ----------


def test_refresh_replay_is_audited_once_per_window(db):
    _, uid = _signup("replayed@example.com")
    c = _login("replayed@example.com")
    old = c.cookies.get("refresh_token")
    assert c.post("/auth/refresh").status_code == 200
    replay = TestClient(app)
    replay.cookies.set("refresh_token", old)
    for _ in range(5):
        assert replay.post("/auth/refresh").status_code == 401
    assert db.query(AuditLog).filter(AuditLog.target_id == uid, AuditLog.action == "session.refresh_replayed").count() == 1

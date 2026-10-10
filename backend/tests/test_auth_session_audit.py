"""Sign-in and session events are on the audit trail, and expired revoked
refresh tokens are pruned: login success/failure/lockout/blocked-deactivated,
logout, replay of a retired refresh token; unknown emails and refused retries
during a lockout are not written to the table; the purge only removes rows
whose token has already expired."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.services.token_cleanup import purge_expired_revoked_tokens


def _signup(email="owner1@example.com"):
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": "owner"})
    assert r.status_code == 201
    return r.json()["id"]


def _actions(db, user_id):
    db.expire_all()
    # created_at has one-second resolution and ids are random uuids, so rows
    # written in the same second have no stable order: compare sorted.
    return sorted(r.action for r in db.query(AuditLog).filter(AuditLog.target_id == user_id).all())


def _login(email, password="password123"):
    c = TestClient(app)
    return c, c.post("/auth/login", json={"email": email, "password": password})


def test_login_success_and_failure_are_audited(db):
    uid = _signup()
    _, r = _login("owner1@example.com", "wrong-password")
    assert r.status_code == 401
    _, r = _login("owner1@example.com")
    assert r.status_code == 200
    assert _actions(db, uid) == sorted(["login.failed", "login.success"])
    row = db.query(AuditLog).filter(AuditLog.action == "login.success").one()
    assert row.actor_id == uid and '"ip"' in row.new_value
    assert "password" not in (row.new_value or "").lower()


def test_unknown_email_is_not_written_to_the_trail(db):
    _login("nobody@example.com", "whatever123")
    assert db.query(AuditLog).filter(AuditLog.action.like("login.%")).count() == 0


def test_lockout_is_audited_once_not_on_every_refused_retry(db):
    uid = _signup()
    for _ in range(5):
        _, r = _login("owner1@example.com", "wrong-password")
        assert r.status_code == 401
    for _ in range(3):
        _, r = _login("owner1@example.com", "wrong-password")
        assert r.status_code == 429
    actions = _actions(db, uid)
    assert actions.count("login.failed") == 5
    assert actions.count("login.locked") == 1


def test_deactivated_account_login_attempt_is_audited(db):
    uid = _signup()
    db.get(User, uid).deactivated_at = datetime.utcnow()
    db.commit()
    _, r = _login("owner1@example.com")
    assert r.status_code == 401
    assert _actions(db, uid) == ["login.blocked_deactivated"]


def test_logout_and_refresh_replay_are_audited(db):
    uid = _signup()
    c, r = _login("owner1@example.com")
    assert r.status_code == 200
    old_refresh = c.cookies.get("refresh_token")

    assert c.post("/auth/refresh").status_code == 200  # rotates; successful refreshes are not audited
    replay = TestClient(app)
    replay.cookies.set("refresh_token", old_refresh)
    assert replay.post("/auth/refresh").status_code == 401  # the retired token coming back

    assert c.post("/auth/logout").status_code == 200
    assert _actions(db, uid) == sorted(["login.success", "session.refresh_replayed", "session.logout"])


def test_purge_removes_only_expired_revoked_tokens(db):
    now = datetime.utcnow()
    db.add_all(
        [
            RevokedToken(jti="expired-1", expires_at=now - timedelta(days=1)),
            RevokedToken(jti="expired-2", expires_at=now - timedelta(seconds=5)),
            RevokedToken(jti="live-1", expires_at=now + timedelta(days=3)),
        ]
    )
    db.commit()
    assert purge_expired_revoked_tokens(db) == 2
    assert [r.jti for r in db.query(RevokedToken).all()] == ["live-1"]
    assert purge_expired_revoked_tokens(db) == 0


def test_purge_works_through_batches(db):
    past = datetime.utcnow() - timedelta(hours=1)
    db.add_all([RevokedToken(jti=f"old-{i}", expires_at=past) for i in range(7)])
    db.commit()
    assert purge_expired_revoked_tokens(db, batch=3, max_batches=1) == 3
    assert purge_expired_revoked_tokens(db, batch=3, max_batches=10) == 4
    assert db.query(RevokedToken).count() == 0


def test_hourly_cron_reports_purged_tokens(db, monkeypatch):
    from app.routers import cron as cron_module

    monkeypatch.setattr(cron_module.settings, "cron_secret", "s3cret", raising=False)
    db.add(RevokedToken(jti="old", expires_at=datetime.utcnow() - timedelta(days=1)))
    db.commit()
    r = TestClient(app).get("/cron/deadline-reminders", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and r.json()["revoked_tokens_purged"] == 1

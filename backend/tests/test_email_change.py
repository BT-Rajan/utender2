"""Changing a sign-in email: a code goes to the CURRENT address and confirming
it switches the account (unverified until the new address is verified); wrong
codes, expiry, supersession, rate limits and taken addresses are handled; an
admin can correct a person's details when they've lost the old mailbox."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.email_change import EmailChangeRequest
from app.models.user import User
from tests.test_stage8_15_review_moderation import _admin

OLD = "old@example.com"
NEW = "new@example.com"


@pytest.fixture
def sent(monkeypatch):
    """Captures what the email functions are asked to send."""
    box = {"codes": [], "verify": [], "changed": []}
    import app.services.email_change as svc
    import app.routers.admin as admin_module

    monkeypatch.setattr(svc, "notify_email_change_code", lambda to, new, code: box["codes"].append((to, new, code)))
    monkeypatch.setattr(svc, "notify_email_changed", lambda old, new: box["changed"].append((old, new)))
    monkeypatch.setattr(svc, "notify_verify_email", lambda to, token: box["verify"].append(to))
    import app.services.email as email_module

    monkeypatch.setattr(email_module, "notify_email_changed", lambda old, new: box["changed"].append((old, new)))
    monkeypatch.setattr(email_module, "notify_verify_email", lambda to, token: box["verify"].append(to))
    return box


def _user(email=OLD):
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": "owner"})
    assert r.status_code == 201
    return c, r.json()["id"]


def _ask(c, new=NEW, password="password123"):
    return c.post("/auth/email-change/request", json={"new_email": new, "current_password": password})


def _backdate(db, minutes=5):
    db.expire_all()
    for r in db.query(EmailChangeRequest).all():
        r.created_at = datetime.utcnow() - timedelta(minutes=minutes)
    db.commit()


def test_happy_path_moves_the_account_to_the_new_email(db, sent):
    c, uid = _user()
    r = _ask(c)
    assert r.status_code == 200 and r.json()["sent_to"] == "o**@example.com"
    to, new, code = sent["codes"][0]
    assert (to, new) == (OLD, NEW)  # the code goes to the CURRENT address

    r = c.post("/auth/email-change/confirm", json={"code": code})
    assert r.status_code == 200 and r.json()["email"] == NEW and r.json()["email_verified"] is False
    assert sent["verify"] == [OLD, NEW][1:] and sent["changed"] == [(OLD, NEW)]

    assert TestClient(app).post("/auth/login", json={"email": NEW, "password": "password123"}).status_code == 200
    assert TestClient(app).post("/auth/login", json={"email": OLD, "password": "password123"}).status_code == 401
    assert c.get("/auth/me").status_code == 200  # the current session carries on
    row = db.query(AuditLog).filter(AuditLog.action == "account.email_changed").one()
    assert (row.actor_id, row.previous_value, row.new_value) == (uid, OLD, NEW)
    # single use
    assert c.post("/auth/email-change/confirm", json={"code": code}).status_code == 400


def test_needs_the_current_password_and_a_different_address(db, sent):
    c, _ = _user()
    assert _ask(c, password="not-my-password").status_code == 400
    assert _ask(c, new="OLD@example.com").status_code == 400
    assert sent["codes"] == []
    assert TestClient(app).post("/auth/email-change/request", json={"new_email": NEW, "current_password": "x"}).status_code == 401


def test_wrong_codes_are_counted_and_lock_the_request(db, sent):
    c, _ = _user()
    _ask(c)
    code = sent["codes"][0][2]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert c.post("/auth/email-change/confirm", json={"code": wrong}).status_code == 400
    r = c.post("/auth/email-change/confirm", json={"code": code})  # even the right code is refused now
    assert r.status_code == 400 and db.query(User).filter(User.email == OLD).count() == 1
    assert c.post("/auth/email-change/confirm", json={"code": "12ab56"}).status_code == 422


def test_expired_code_is_refused(db, sent):
    c, _ = _user()
    _ask(c)
    db.expire_all()
    req = db.query(EmailChangeRequest).one()
    req.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert c.post("/auth/email-change/confirm", json={"code": sent["codes"][0][2]}).status_code == 400
    assert db.query(User).filter(User.email == OLD).count() == 1


def test_a_new_request_supersedes_the_old_code_and_is_rate_limited(db, sent):
    c, _ = _user()
    assert _ask(c).status_code == 200
    r = _ask(c, new="third@example.com")
    assert r.status_code == 429 and "Retry-After" in r.headers  # cooldown
    _backdate(db)
    assert _ask(c, new="third@example.com").status_code == 200
    first, second = sent["codes"][0][2], sent["codes"][1][2]
    if first != second:
        assert c.post("/auth/email-change/confirm", json={"code": first}).status_code == 400
    r = c.post("/auth/email-change/confirm", json={"code": second})
    assert r.status_code == 200 and r.json()["email"] == "third@example.com"


def test_hourly_cap(db, sent):
    c, uid = _user()
    for _ in range(5):
        db.add(EmailChangeRequest(user_id=uid, new_email=NEW, code_hash="x", expires_at=datetime.utcnow(),
                                  consumed_at=datetime.utcnow(), created_at=datetime.utcnow() - timedelta(minutes=10)))
    db.commit()
    assert _ask(c).status_code == 429


def test_an_address_taken_meanwhile_is_refused_and_nothing_changes(db, sent):
    c, _ = _user()
    _ask(c)
    _user(NEW)  # someone else signs up with it before the code is entered
    r = c.post("/auth/email-change/confirm", json={"code": sent["codes"][0][2]})
    assert r.status_code == 409
    db.expire_all()
    assert db.query(User).filter(User.email == OLD).count() == 1


# ---------------- admin ----------------


def test_admin_can_correct_details_and_change_email(db, sent):
    admin = _admin(db)
    _, uid = _user()
    r = admin.patch(f"/admin/users/{uid}", json={"email": "Fresh@Example.com", "full_name": " Noura ", "phone": "+965 1234", "language": "ar", "reason": "lost old mailbox"})
    assert r.status_code == 200
    body = r.json()
    assert (body["email"], body["full_name"], body["phone"], body["language"], body["email_verified"]) == ("fresh@example.com", "Noura", "+965 1234", "ar", False)
    assert sent["verify"] == ["fresh@example.com"] and sent["changed"] == [(OLD, "fresh@example.com")]
    assert TestClient(app).post("/auth/login", json={"email": "fresh@example.com", "password": "password123"}).status_code == 200
    row = db.query(AuditLog).filter(AuditLog.action == "account.updated_by_admin").one()
    assert row.reason == "lost old mailbox" and OLD in row.previous_value and "fresh@example.com" in row.new_value
    assert row.actor_id != uid


def test_admin_edit_guards(db, sent):
    admin = _admin(db)
    c, uid = _user()
    _user("taken@example.com")
    assert admin.patch(f"/admin/users/{uid}", json={"email": "taken@example.com"}).status_code == 409
    assert admin.patch(f"/admin/users/{uid}", json={}).status_code == 400
    assert admin.patch(f"/admin/users/{uid}", json={"email": OLD}).status_code == 400  # same value: nothing to change
    assert admin.patch(f"/admin/users/{uid}", json={"full_name": "  "}).status_code == 400
    assert admin.patch(f"/admin/users/{uid}", json={"email": "not-an-email"}).status_code == 422
    assert admin.patch("/admin/users/missing", json={"full_name": "X"}).status_code == 404
    assert c.patch(f"/admin/users/{uid}", json={"full_name": "X"}).status_code == 403  # not an admin
    assert admin.patch(f"/admin/users/{uid}", json={"role": "admin"}).status_code == 400  # role isn't editable: nothing else sent
    db.expire_all()
    assert db.get(User, uid).email == OLD and db.get(User, uid).role.value == "owner"


def test_admin_cannot_edit_another_admin(db, sent):
    admin = _admin(db)
    admin_id = admin.get("/auth/me").json()["id"]
    assert admin.patch(f"/admin/users/{admin_id}", json={"full_name": "X"}).status_code == 404

"""Stage 9.11: production safety that earlier stages didn't already prove --
browser protections on every response, production refusing development
defaults and hiding the API docs, a hung email provider not holding a
request open, internal errors told safely, and forged, expired or superseded
tokens refused. (IDOR, cross-organisation, confidentiality, file and admin
boundaries are covered by the stage tests re-run with this one.)"""
import os
import subprocess
import sys
import time
import types
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
import jwt

from app.config import Settings, get_settings
from app.main import app
from app.models.email_failure import EmailFailure
from app.services import email as email_service
from tests.test_stage4_9_participation import _account
from tests.test_stage8_15_review_moderation import _admin

GOOD = dict(environment="production", jwt_secret="x" * 64, storage_signing_secret="y" * 64,
            database_url="mysql+pymysql://app:s3cret@db.internal/utender", app_url="https://u-tender.example",
            api_url="https://api.u-tender.example", cors_origins="https://u-tender.example")


def test_production_hardening(db, monkeypatch, caplog):
    owner = _account(db, "owner", "owner@example.com")

    # Browser protections on every response.
    r = owner.get("/auth/me")
    assert (r.headers["x-content-type-options"], r.headers["x-frame-options"], r.headers["referrer-policy"]) == ("nosniff", "DENY", "no-referrer")

    # Production refuses development defaults; a proper configuration starts.
    Settings(**GOOD)
    for bad in ({"app_url": "http://localhost:5173"}, {"cors_origins": "http://localhost:5173"}, {"jwt_secret": "change-me-in-production"}):
        with pytest.raises(ValueError):
            Settings(**{**GOOD, **bad})
    # Risky but possibly how a live server runs today (deploy.sh is plain http): started, loudly warned.
    import logging

    with caplog.at_level(logging.WARNING, logger="config"):
        Settings(**{**GOOD, "database_url": "mysql+pymysql://utender:utender@db/utender", "app_url": "http://203.0.113.5:5173"})
    assert "development credentials" in caplog.text and "aren't Secure" in caplog.text

    # In production the interactive API description isn't served.
    env = {**os.environ, **{k.upper(): v for k, v in GOOD.items()}}
    env["APP_URL"] = "https://u-tender.example"
    probe = ("from fastapi.testclient import TestClient; from app.main import app; c = TestClient(app); "
             "print(c.get('/docs').status_code, c.get('/openapi.json').status_code, c.get('/health').status_code)")
    out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=60, cwd=os.getcwd())
    assert out.stdout.split() == ["404", "404", "200"], out.stderr[-500:]

    # A hung email provider doesn't hold the request: bounded, then recorded as a failure.
    monkeypatch.setattr(get_settings(), "resend_api_key", "test-key")
    monkeypatch.setattr(email_service, "SEND_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setitem(sys.modules, "resend", types.SimpleNamespace(api_key=None, Emails=types.SimpleNamespace(send=lambda msg: time.sleep(3))))
    start = time.monotonic()
    email_service._send("someone@example.com", "Subject", "<p>x</p>")
    assert time.monotonic() - start < 2
    assert db.query(EmailFailure).filter(EmailFailure.subject == "Subject").count() == 1

    # An internal error is told safely -- no message, trace or internals.
    import app.services.operations as operations

    monkeypatch.setattr(operations, "overview", lambda db: (_ for _ in ()).throw(RuntimeError("password=hunter2 at db.internal")))
    admin = _admin(db)
    quiet = TestClient(app, raise_server_exceptions=False)
    quiet.cookies.update(admin.cookies)
    r = quiet.get("/admin/overview")
    assert r.status_code == 500 and "hunter2" not in r.text and "Traceback" not in r.text and "db.internal" not in r.text

    # Tokens: forged, expired, or issued before a password change -- all refused.
    s = get_settings()
    uid = owner.get("/auth/me").json()["id"]
    forged = TestClient(app)
    forged.cookies.set("access_token", jwt.encode({"sub": uid, "type": "access"}, "not-the-secret", algorithm="HS256"))
    assert forged.get("/auth/me").status_code == 401
    expired = TestClient(app)
    expired.cookies.set("access_token", jwt.encode({"sub": uid, "type": "access", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, s.jwt_secret, algorithm=s.jwt_algorithm))
    assert expired.get("/auth/me").status_code == 401
    old = TestClient(app)
    old.cookies.update(owner.cookies)
    assert owner.post("/auth/change-password", json={"current_password": "password123", "new_password": "password456"}).status_code == 200
    assert old.get("/auth/me").status_code == 401  # the session from before the change is dead
    assert TestClient(app).post("/billing/webhook", content=b"{}").status_code == 400  # unsigned webhook

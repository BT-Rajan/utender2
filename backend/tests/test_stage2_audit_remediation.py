"""Regression tests for the Stage 1 audit remediation (Prompt 02).

One section per remediation item (R1..R9). Each test drives the real API
path -- not helper functions -- so it proves the boundary, not just the unit.
"""
import io
import json
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.auth.router as auth_router_module
from app.auth.security import hash_password
from app.config import Settings
from app.main import app
from app.middleware import MaxBodySizeMiddleware
from app.models.audit_log import AuditLog
from app.models.service_provider import ServiceProviderProfile
from app.models.enums import AuthTokenType, UserRole, VerificationStatus
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project, ProjectDrawing
from app.models.user import User
from app.services.auth_tokens import issue_token

PASSWORD = "password123"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _future() -> str:
    return (datetime.utcnow() + timedelta(days=7)).replace(microsecond=0).isoformat()


def _owner(db, email="owner@example.com"):
    client = TestClient(app)
    r = client.post("/auth/signup", json={"email": email, "password": PASSWORD, "full_name": "Owner", "role": "owner"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    db.get(OwnerProfile, uid).verification_status = VerificationStatus.approved
    db.commit()
    return client, uid


def _service_provider(db, email="c1@example.com", company="Acme Builders"):
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={"email": email, "password": PASSWORD, "full_name": "ServiceProvider", "role": "service_provider", "company_name": company},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    profile = db.get(ServiceProviderProfile, uid)
    profile.verification_status = VerificationStatus.approved
    profile.payment_override_active = True
    db.commit()
    return client, uid


def _admin(db):
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    client = TestClient(app)
    r = client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    assert r.status_code == 200, r.text
    return client, r.json()["id"]


def _project(owner, tender_type="owner_visible", status="open") -> str:
    r = owner.post(
        "/projects",
        data={"title": "Job", "address": "1 Main St", "bid_deadline": _future(), "status": status, "tender_type": tender_type},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _bid(service_provider, project_id, amount="1000.00") -> str:
    r = service_provider.post(f"/projects/{project_id}/offers", json={"amount": amount})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# --------------------------------------------------------------------------
# R1 (P0) -- an owner must not be able to unseal a sealed tender early
# --------------------------------------------------------------------------


def test_r1_owner_cannot_close_a_sealed_tender_before_its_deadline(db):
    owner, _ = _owner(db)
    c1, _ = _service_provider(db)
    pid = _project(owner, "sealed")
    _bid(c1, pid, "5000.00")

    r = owner.post(f"/owner/projects/{pid}/close")

    assert r.status_code == 400, r.text
    db.expire_all()
    assert db.get(Project, pid).status.value == "open"
    offers = owner.get(f"/owner/projects/{pid}/offers").json()
    assert offers and all(o["amount"] is None and o["service_provider_id"] is None and o["sealed"] is True for o in offers)


def test_r1_owner_visible_tender_can_still_be_closed_early(db):
    owner, _ = _owner(db)
    pid = _project(owner, "owner_visible")

    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200


def test_r1_sealed_tender_opens_normally_when_its_deadline_passes(db):
    owner, _ = _owner(db)
    c1, _ = _service_provider(db)
    pid = _project(owner, "sealed")
    _bid(c1, pid, "5000.00")

    project = db.get(Project, pid)
    project.bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner.get("/owner/projects")  # lazy deadline sync, as the app does on any read

    offers = owner.get(f"/owner/projects/{pid}/offers").json()
    assert offers and all(o["amount"] is not None and o["sealed"] is False for o in offers)


# --------------------------------------------------------------------------
# R2 (P0) -- admin bid edits: state guards + a useful audit trail
# --------------------------------------------------------------------------


def test_r2_admin_cannot_edit_an_awarded_offer(db):
    owner, _ = _owner(db)
    c1, _ = _service_provider(db)
    admin, _ = _admin(db)
    pid = _project(owner)
    offer_id = _bid(c1, pid, "1000.00")
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve").status_code == 200

    r = admin.patch(f"/admin/offers/{offer_id}", json={"amount": "1.00"})

    assert r.status_code == 400, r.text
    db.expire_all()
    assert db.get(Offer, offer_id).amount == Decimal("1000.00")


def test_r2_admin_cannot_edit_a_bid_while_its_tender_is_sealed_and_open(db):
    owner, _ = _owner(db)
    c1, _ = _service_provider(db)
    admin, _ = _admin(db)
    pid = _project(owner, "sealed")
    offer_id = _bid(c1, pid, "5000.00")

    r = admin.patch(f"/admin/offers/{offer_id}", json={"amount": "1.00"})

    assert r.status_code == 400, r.text
    db.expire_all()
    assert db.get(Offer, offer_id).amount == Decimal("5000.00")


def test_r2_admin_edit_still_works_and_audit_records_old_and_new_values(db):
    owner, _ = _owner(db)
    c1, _ = _service_provider(db)
    admin, admin_id = _admin(db)
    pid = _project(owner, "owner_visible")
    offer_id = _bid(c1, pid, "1000.00")

    r = admin.patch(f"/admin/offers/{offer_id}", json={"amount": "1200.00"})

    assert r.status_code == 200, r.text
    db.expire_all()
    row = db.query(AuditLog).filter_by(action="offer.admin_edit", target_id=offer_id).one()
    assert row.actor_id == admin_id
    assert Decimal(json.loads(row.previous_value)["amount"]) == Decimal("1000.00")
    assert Decimal(json.loads(row.new_value)["amount"]) == Decimal("1200.00")


# --------------------------------------------------------------------------
# R3 (P1) -- admin deletes leave an audit trail
# --------------------------------------------------------------------------


def test_r3_admin_deleting_a_project_and_an_offer_is_audited(db):
    owner, _ = _owner(db)
    c1, _ = _service_provider(db)
    admin, admin_id = _admin(db)

    empty_pid = _project(owner)
    assert admin.delete(f"/admin/projects/{empty_pid}").status_code == 204

    bid_pid = _project(owner)
    offer_id = _bid(c1, bid_pid, "900.00")
    assert admin.delete(f"/admin/offers/{offer_id}").status_code == 204

    db.expire_all()
    p_row = db.query(AuditLog).filter_by(action="project.admin_delete", target_id=empty_pid).one()
    assert p_row.actor_id == admin_id and "Job" in (p_row.previous_value or "")
    o_row = db.query(AuditLog).filter_by(action="offer.admin_delete", target_id=offer_id).one()
    assert o_row.actor_id == admin_id


# --------------------------------------------------------------------------
# R4 (P1) -- hostile file names never reach storage metadata or the download zip
# --------------------------------------------------------------------------


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_r4_zip_entry_names_are_normalised_and_disallowed_types_skipped(db):
    owner, _ = _owner(db)
    pid = _project(owner)
    data = _zip_bytes(
        {
            "../../evil.pdf": b"%PDF-1",
            "/abs/abs.pdf": b"%PDF-2",
            "ok/plan.pdf": b"%PDF-3",
            "run.exe": b"MZ",
            "page.html": b"<html></html>",
        }
    )

    r = owner.post(f"/projects/{pid}/drawings", files={"drawings": ("pack.zip", data, "application/zip")})

    assert r.status_code == 200, r.text
    db.expire_all()
    names = {d.file_name for d in db.query(ProjectDrawing).filter_by(project_id=pid)}
    assert names == {"evil.pdf", "abs/abs.pdf", "ok/plan.pdf"}


def test_r4_plain_upload_with_a_hostile_filename_is_normalised(db):
    owner, _ = _owner(db)
    pid = _project(owner)

    r = owner.post(f"/projects/{pid}/drawings", files={"drawings": ("../../x.pdf", b"%PDF-1", "application/pdf")})

    assert r.status_code == 200, r.text
    db.expire_all()
    assert {d.file_name for d in db.query(ProjectDrawing).filter_by(project_id=pid)} == {"x.pdf"}


def test_r4_download_zip_never_contains_unsafe_member_names_even_for_legacy_rows(db):
    owner, _ = _owner(db)
    pid = _project(owner)
    owner.post(f"/projects/{pid}/drawings", files={"drawings": ("ok.pdf", b"%PDF-1", "application/pdf")})
    # A row written before this fix could hold a hostile name already.
    drawing = db.query(ProjectDrawing).filter_by(project_id=pid).one()
    drawing.file_name = "../../legacy.pdf"
    db.commit()

    r = owner.get(f"/projects/{pid}/drawings-zip")

    assert r.status_code == 200, r.text
    members = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert members == ["legacy.pdf"]


# --------------------------------------------------------------------------
# R5 (P1) -- production refuses default secrets; cookies get Secure when served over https
# --------------------------------------------------------------------------

_DEFAULT = "change-me-in-production"


def test_r5_production_refuses_default_secrets():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", jwt_secret=_DEFAULT, storage_signing_secret="s" * 32)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", jwt_secret="j" * 32, storage_signing_secret=_DEFAULT)

    ok = Settings(_env_file=None, environment="production", jwt_secret="j" * 32, storage_signing_secret="s" * 32,
                  # Stage 9.11: production also refuses localhost URLs and non-Secure cookies.
                  app_url="https://u-tender.example", api_url="https://api.u-tender.example", cors_origins="https://u-tender.example")
    assert ok.environment == "production"
    # Local development keeps working with the placeholder defaults.
    Settings(_env_file=None, environment="development")


@pytest.mark.parametrize(
    "app_url, override, expect_secure",
    [
        ("https://app.example.com", None, True),
        ("http://localhost:5173", None, False),
        ("https://app.example.com", False, False),
        ("http://intranet.example.com", True, True),
    ],
)
def test_r5_auth_cookie_secure_flag_follows_configuration(db, monkeypatch, app_url, override, expect_secure):
    cfg = auth_router_module.settings
    monkeypatch.setattr(cfg, "app_url", app_url)
    monkeypatch.setattr(cfg, "cookie_secure", override)
    TestClient(app).post(
        "/auth/signup", json={"email": "cookie@example.com", "password": PASSWORD, "full_name": "C", "role": "owner"}
    )
    client = TestClient(app)

    r = client.post("/auth/login", json={"email": "cookie@example.com", "password": PASSWORD})

    assert r.status_code == 200, r.text
    cookies = r.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all(("secure" in c.lower()) is expect_secure for c in cookies), cookies


# --------------------------------------------------------------------------
# R6 (P1) -- login throttling
# --------------------------------------------------------------------------


def _make_user(email):
    TestClient(app).post("/auth/signup", json={"email": email, "password": PASSWORD, "full_name": "U", "role": "owner"})


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_r6_login_is_locked_after_repeated_failures_even_for_the_right_password(db):
    _make_user("victim@example.com")
    client = TestClient(app)

    for _ in range(5):
        assert _login(client, "victim@example.com", "wrong-password").status_code == 401
    blocked = _login(client, "victim@example.com", "wrong-password")
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert _login(client, "victim@example.com", PASSWORD).status_code == 429


def test_r6_successful_login_resets_the_failure_count(db):
    _make_user("u@example.com")
    client = TestClient(app)

    for _ in range(4):
        assert _login(client, "u@example.com", "wrong-password").status_code == 401
    assert _login(client, "u@example.com", PASSWORD).status_code == 200
    for _ in range(4):
        assert _login(client, "u@example.com", "wrong-password").status_code == 401


def test_r6_lockout_is_per_account_not_global(db):
    _make_user("locked@example.com")
    _make_user("other@example.com")
    client = TestClient(app)
    for _ in range(6):
        _login(client, "locked@example.com", "wrong-password")

    assert _login(client, "other@example.com", PASSWORD).status_code == 200


# --------------------------------------------------------------------------
# R7 (P1) -- a suspended owner cannot amend a tender or upload drawings
# --------------------------------------------------------------------------


def test_r7_suspended_owner_cannot_amend_or_add_drawings(db):
    owner, uid = _owner(db)
    pid = _project(owner)
    db.get(OwnerProfile, uid).is_suspended = True
    db.commit()

    assert owner.patch(f"/projects/{pid}", json={"title": "Changed title"}).status_code == 403
    r = owner.post(f"/projects/{pid}/drawings", files={"drawings": ("a.pdf", b"%PDF-1", "application/pdf")})
    assert r.status_code == 403

    db.expire_all()
    assert db.get(Project, pid).title == "Job"
    assert db.query(ProjectDrawing).filter_by(project_id=pid).count() == 0

    db.get(OwnerProfile, uid).is_suspended = False
    db.commit()
    assert owner.patch(f"/projects/{pid}", json={"title": "Changed title"}).status_code == 200


# --------------------------------------------------------------------------
# R8 (P1) -- changing/resetting a password ends the account's other sessions
# --------------------------------------------------------------------------


def test_r8_changing_password_invalidates_other_sessions_but_not_the_current_one(db):
    current = TestClient(app)
    r = current.post("/auth/signup", json={"email": "sess@example.com", "password": PASSWORD, "full_name": "S", "role": "owner"})
    assert r.status_code == 201
    other = TestClient(app)
    assert _login(other, "sess@example.com", PASSWORD).status_code == 200
    assert other.get("/auth/me").status_code == 200

    r = current.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": "newpassword456"})
    assert r.status_code == 200, r.text

    assert current.get("/auth/me").status_code == 200
    assert other.get("/auth/me").status_code == 401
    assert other.post("/auth/refresh").status_code == 401


def test_r8_password_reset_invalidates_existing_sessions(db):
    victim_session = TestClient(app)
    r = victim_session.post(
        "/auth/signup", json={"email": "reset@example.com", "password": PASSWORD, "full_name": "R", "role": "owner"}
    )
    uid = r.json()["id"]
    assert victim_session.get("/auth/me").status_code == 200

    token = issue_token(db, uid, AuthTokenType.password_reset)
    r = TestClient(app).post("/auth/reset-password", json={"token": token, "new_password": "brandnewpass1"})
    assert r.status_code == 200, r.text

    assert victim_session.get("/auth/me").status_code == 401
    assert _login(TestClient(app), "reset@example.com", "brandnewpass1").status_code == 200


# --------------------------------------------------------------------------
# R9 (P2) -- the body cap counts bytes actually received, not just the header
# --------------------------------------------------------------------------


def test_r9_body_cap_applies_to_chunked_bodies_without_content_length():
    inner = FastAPI()

    @inner.post("/echo")
    async def echo(request: Request):
        return {"n": len(await request.body())}

    inner.add_middleware(MaxBodySizeMiddleware, max_body_bytes=1024)
    client = TestClient(inner)

    def chunks():
        for _ in range(8):
            yield b"x" * 512  # 4096 bytes total, streamed: no Content-Length header

    assert client.post("/echo", content=chunks()).status_code == 413
    assert client.post("/echo", content=b"x" * 2000).status_code == 413  # declared-length path
    ok = client.post("/echo", content=b"x" * 100)
    assert ok.status_code == 200 and ok.json() == {"n": 100}

"""Stage 9.2: people and organisations through their lifecycle. A member who
leaves loses the organisation at once while it and its records stay; an
organisation suspended stops new actions and everyone acting for it is told;
an admin can deactivate one person -- every session at once, no sign-in --
and reactivate them exactly as they were; admins see an organisation's
members, and no longer see members' own rows as stakeholders."""
from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.review import Review
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_7_provider_reputation import _award
from tests.test_stage8_15_review_moderation import _admin


def _login(email):
    c = TestClient(app)
    return c, c.post("/auth/login", json={"email": email, "password": "password123"})


def test_people_and_organisations_through_their_lifecycle(db):
    admin = _admin(db)
    owner, noura, owner_id, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, x_id, sami_id = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    other = _account(db, "owner", "other@example.com")
    pid = _tender(owner, title="Tower maintenance")
    _award(owner, sami, pid)
    complete_transaction(owner, sami, pid)
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 4}).status_code == 200

    # A. Sami leaves X: loses it at once; X, Amal and the records stay as they were.
    assert amal.delete(f"/account/organization/members/{sami_id}").status_code == 200
    for path in (f"/projects/{pid}/agreement", f"/service-provider/projects/{pid}/review/received"):
        assert sami.get(path).status_code in (403, 404)
        assert amal.get(path).status_code == 200
    assert db.query(AwardRecord).filter(AwardRecord.project_id == pid).one().service_provider_id == x_id
    assert db.query(Review).one().service_provider_id == x_id
    assert amal.get("/service-provider/reputation").json()["completed_transactions"] == 1

    # Admin sees the organisation's people; members' own rows aren't listed or managed as stakeholders.
    detail = admin.get(f"/admin/owners/{owner_id}").json()
    assert [(m["email"], m["role"], m["deactivated_at"]) for m in detail["members"]] == [
        ("fahad@gulf.example", "admin", None), ("noura@gulf.example", "member", None)]
    assert noura_id not in {o["user_id"] for o in admin.get("/admin/owners").json()}
    assert owner_id in {o["user_id"] for o in admin.get("/admin/owners").json()}
    assert admin.post(f"/admin/owners/{noura_id}/suspend", json={"suspended": True}).status_code == 409

    # C. Noura's account is deactivated: her live session stops, sign-in and refresh are refused.
    assert noura.get(f"/projects/{pid}").status_code == 200
    for _ in range(2):  # repeated: one change, one audit entry
        r = admin.post(f"/admin/users/{noura_id}/deactivate", json={"reason": "Left the company"})
        assert r.status_code == 200 and r.json()["deactivated_at"]
    assert db.query(AuditLog).filter(AuditLog.action == "account.deactivate", AuditLog.target_id == noura_id).count() == 1
    me = noura.get("/auth/me")
    assert me.status_code == 401 and "deactivated" in me.json()["detail"]
    assert noura.get(f"/projects/{pid}").status_code == 401
    assert noura.post("/auth/refresh").status_code == 401
    _, login = _login("noura@gulf.example")
    assert login.status_code == 401 and "deactivated" in login.json()["detail"]
    # The organisation and its other member carry on; nothing was removed.
    assert owner.get(f"/projects/{pid}").status_code == 200
    assert [m["email"] for m in owner.get("/account/organization/members").json()] == ["fahad@gulf.example", "noura@gulf.example"]

    # D. Reactivated: back exactly as before -- the same organisation, the same (member) rights.
    assert admin.post(f"/admin/users/{noura_id}/reactivate").status_code == 200
    noura2, login = _login("noura@gulf.example")
    assert login.status_code == 200 and noura2.get(f"/projects/{pid}").status_code == 200
    assert noura2.post("/account/organization/invitations", json={"email": "new@gulf.example"}).status_code == 403  # still a member, not the representative

    # B. X is suspended: new actions stop, everyone acting for X is told, history stays.
    assert admin.post(f"/admin/service-providers/{x_id}/suspend", json={"suspended": True}).status_code == 200
    told = {n.user_id for n in db.query(Notification).filter(Notification.type == NotificationType.service_provider_suspended)}
    assert told == {x_id}  # Sami left before; only current members are told
    assert admin.post(f"/admin/owners/{owner_id}/suspend", json={"suspended": True}).status_code == 200
    told = {n.user_id for n in db.query(Notification).filter(Notification.type == NotificationType.owner_suspended)}
    assert told == {owner_id, noura_id}
    assert owner.post("/projects", data={"title": "New", "address": "A", "bid_deadline": "2030-01-01T00:00:00", "status": "open"}).status_code == 403
    assert owner.get(f"/projects/{pid}").status_code == 200  # its history stays readable to it
    assert db.query(AwardRecord).filter(AwardRecord.project_id == pid).one().service_provider_id == x_id

    # IDOR: nobody but an admin changes accounts; admins aren't managed here; unknown ids are refused.
    for c in (owner, noura2, amal, other):
        assert c.post(f"/admin/users/{noura_id}/deactivate").status_code == 403
    assert other.delete(f"/account/organization/members/{noura_id}").status_code in (400, 403)
    admin_id = admin.get("/auth/me").json()["id"]
    assert admin.post(f"/admin/users/{admin_id}/deactivate").status_code == 404
    assert admin.post("/admin/users/no-such-user/deactivate").status_code == 404
    assert TestClient(app).post(f"/admin/users/{noura_id}/deactivate").status_code == 401

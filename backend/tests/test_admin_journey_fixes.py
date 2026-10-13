"""Admin-journey audit fixes. Each test is one logic gap found in the review
of the administrator's journey, now corrected:

1. a refused account deletion changes nothing: the account's stored files are
   removed only once the deletion itself is committed;
2. the owner's 30 days to answer don't run while an admin has the owner
   account suspended or its login deactivated (as for a suspended requirement);
3. the manual verification-status control follows the review rules: approval
   needs every required document approved, a send-back or rejection says
   why, the account holder is told, and the applicant's own states
   (incomplete, pending review) aren't set by hand;
4. sending back an optional qualification of a verified provider that is
   suspended decides that document only -- the suspension doesn't undo the
   verification -- and a document decision that does send an application
   back is on the account's trail;
5. a rejected application isn't silently reopened by a decision on one of
   its documents: it is reopened by requesting changes first."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.agreement import Agreement
from app.models.audit_log import AuditLog
from app.models.document import ServiceProviderDocument
from app.models.enums import NotificationType, UserRole, VerificationStatus
from app.models.notification import Notification
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from app.services.storage import get_storage
from tests.stage7_helpers import put_in_force
from tests.test_provider_journey_fixes import _awarded_to
from tests.test_batch_a_contract_logic import _v
from tests.test_stage4_9_participation import _account

PDF = {"file": ("doc.pdf", b"%PDF-1.4 test", "application/pdf")}


def _admin(db, email="admin-fixes@example.com"):
    db.add(User(email=email, password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin"))
    db.commit()
    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "adminpass123"}).status_code == 200
    return c


def _register(role, email):
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "P", "role": role})
    assert r.status_code == 201, r.text
    assert c.put("/account/stakeholder", json={"type": "individual"}).status_code == 200
    return c, r.json()["id"]


def _verified_provider(db, admin, email="sp-fixes@example.com"):
    required = admin.post("/admin/requirements", json={"name": "Licence", "applies_to": "service_provider", "is_required": True}).json()
    optional = admin.post("/admin/requirements", json={"name": "ISO cert", "applies_to": "service_provider", "is_required": False}).json()
    sp, sp_id = _register("service_provider", email)
    assert sp.post(f"/service-provider/documents/{required['id']}/upload", files=PDF).status_code == 200
    assert sp.post("/service-provider/submit-for-review", json={"company_name": "Acme"}).status_code == 200
    assert admin.post("/admin/review/documents", json={"service_provider_id": sp_id, "requirement_id": required["id"], "decision": "approved"}).status_code == 200
    assert admin.post(f"/admin/review/service-providers/{sp_id}/approve").status_code == 200
    return sp, sp_id, required, optional


# 1 -------------------------------------------------------------------------
def test_a_refused_provider_deletion_keeps_its_files(db):
    admin = _admin(db)
    req = admin.post("/admin/requirements", json={"name": "Licence", "applies_to": "service_provider"}).json()
    sp, sp_id = _register("service_provider", "sp-del@example.com")
    assert sp.post(f"/service-provider/documents/{req['id']}/upload", files=PDF).status_code == 200
    # A recorded action of its own (a password change) means it can't be deleted.
    assert sp.post("/auth/change-password", json={"current_password": "password123", "new_password": "password456"}).status_code == 200
    path = db.query(ServiceProviderDocument).filter_by(service_provider_id=sp_id).one().file_path
    assert admin.delete(f"/admin/service-providers/{sp_id}").status_code == 400
    assert get_storage().exists("service-provider-documents", path)


def test_a_deleted_provider_s_files_go_with_it(db):
    admin = _admin(db)
    req = admin.post("/admin/requirements", json={"name": "Licence", "applies_to": "service_provider"}).json()
    sp, sp_id = _register("service_provider", "sp-del2@example.com")
    assert sp.post(f"/service-provider/documents/{req['id']}/upload", files=PDF).status_code == 200
    path = db.query(ServiceProviderDocument).filter_by(service_provider_id=sp_id).one().file_path
    # An account that never acted (its own sign-up entries cleared here) is deletable.
    db.query(AuditLog).filter(AuditLog.actor_id == sp_id).delete()
    db.commit()
    assert admin.delete(f"/admin/service-providers/{sp_id}").status_code == 204
    assert not get_storage().exists("service-provider-documents", path)


# 2 -------------------------------------------------------------------------
def test_the_owners_30_days_dont_run_while_the_owner_account_is_suspended(db):
    owner = _account(db, "owner", "o-acct-paused@example.com")
    owner_id = owner.get("/auth/me").json()["id"]
    sp = _account(db, "service_provider", "s-acct-paused@example.com")
    pid = _awarded_to(db, owner, sp)
    base = f"/projects/{pid}/agreement"
    put_in_force(owner, sp, pid)
    sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid))
    assert sp.post(f"{base}/completion/submit", json={}, headers=_v(sp, pid)).status_code == 200
    now = datetime.utcnow()
    db.query(Agreement).filter(Agreement.project_id == pid).update({Agreement.completion_submitted_at: now - timedelta(days=31)})
    # The owner account was suspended for 15 of those days, and its login
    # deactivated for 10 (5 of them overlapping): 20 days it couldn't answer.
    db.add_all([
        AuditLog(action="owner.suspend", target_type="owner_profile", target_id=owner_id, created_at=now - timedelta(days=30)),
        AuditLog(action="owner.reactivate", target_type="owner_profile", target_id=owner_id, created_at=now - timedelta(days=15)),
        AuditLog(action="account.deactivate", target_type="user", target_id=owner_id, created_at=now - timedelta(days=20)),
        AuditLog(action="account.reactivate", target_type="user", target_id=owner_id, created_at=now - timedelta(days=10)),
    ])
    db.commit()
    assert sp.get(base).json()["completion_review_overdue"] is False
    assert sp.post(f"{base}/terminate", json={"reason": "No answer"}, headers=_v(sp, pid)).status_code == 409
    # 31 + 20 days on, the owner has had its 30 (overlaps counted once, not 25 days off).
    db.query(Agreement).filter(Agreement.project_id == pid).update({Agreement.completion_submitted_at: now - timedelta(days=50, hours=1)})
    db.commit()
    assert sp.get(base).json()["completion_review_overdue"] is True


# 3 -------------------------------------------------------------------------
def test_the_manual_verification_control_follows_the_review_rules(db):
    admin = _admin(db)
    admin.post("/admin/requirements", json={"name": "Licence", "applies_to": "service_provider", "is_required": True})
    sp, sp_id = _register("service_provider", "sp-override@example.com")
    url = f"/admin/service-providers/{sp_id}/verification-status"
    # Nothing uploaded: not approvable by hand either.
    assert admin.post(url, json={"status": "approved"}).status_code == 400
    # The applicant's own states aren't set by hand.
    assert admin.post(url, json={"status": "pending_review"}).status_code == 400
    # A rejection gives its reason, and the provider is told.
    assert admin.post(url, json={"status": "rejected"}).status_code == 400
    r = admin.post(url, json={"status": "rejected", "note": "Not a contractor"})
    assert r.status_code == 200, r.text
    db.expire_all()
    profile = db.get(ServiceProviderProfile, sp_id)
    assert profile.verification_status == VerificationStatus.rejected and profile.verification_note == "Not a contractor"
    assert db.query(Notification).filter(Notification.user_id == sp_id, Notification.type == NotificationType.verification_rejected).count() == 1
    # Reopened by requesting changes, with a reason.
    assert admin.post(url, json={"status": "changes_requested", "note": "Upload the licence"}).status_code == 200
    db.expire_all()
    assert db.get(ServiceProviderProfile, sp_id).verification_status == VerificationStatus.changes_requested


def test_the_owner_verification_control_follows_the_review_rules(db):
    admin = _admin(db)
    admin.post("/admin/requirements", json={"name": "Civil ID", "applies_to": "owner", "is_required": True})
    ow, ow_id = _register("owner", "ow-override@example.com")
    assert admin.post(f"/admin/owners/{ow_id}/verification-status", json={"status": "approved"}).status_code == 400
    db.expire_all()
    assert db.get(OwnerProfile, ow_id).verification_status != VerificationStatus.approved


# 4 -------------------------------------------------------------------------
def test_sending_back_a_suspended_providers_added_qualification_keeps_its_verification(db):
    admin = _admin(db)
    sp, sp_id, _, optional = _verified_provider(db, admin)
    assert sp.post(f"/service-provider/documents/{optional['id']}/upload", files=PDF).status_code == 200
    assert admin.post(f"/admin/service-providers/{sp_id}/suspend", json={"suspended": True}).status_code == 200
    r = admin.post("/admin/review/documents", json={"service_provider_id": sp_id, "requirement_id": optional["id"], "decision": "rejected", "note": "blurry"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(ServiceProviderProfile, sp_id).verification_status == VerificationStatus.approved
    assert admin.post(f"/admin/service-providers/{sp_id}/suspend", json={"suspended": False}).status_code == 200
    db.expire_all()
    assert db.get(ServiceProviderProfile, sp_id).verification_status == VerificationStatus.approved


def test_a_document_decision_that_sends_an_application_back_is_on_its_trail(db):
    admin = _admin(db)
    req = admin.post("/admin/requirements", json={"name": "Licence", "applies_to": "service_provider", "is_required": True}).json()
    sp, sp_id = _register("service_provider", "sp-trail@example.com")
    assert sp.post(f"/service-provider/documents/{req['id']}/upload", files=PDF).status_code == 200
    assert sp.post("/service-provider/submit-for-review", json={"company_name": "Acme"}).status_code == 200
    admin.post("/admin/review/documents", json={"service_provider_id": sp_id, "requirement_id": req["id"], "decision": "rejected", "note": "blurry"})
    entry = db.query(AuditLog).filter(AuditLog.action == "verification_status.set", AuditLog.target_id == sp_id).one()
    assert entry.previous_value == "pending_review" and entry.new_value.startswith("changes_requested")


# 5 -------------------------------------------------------------------------
def test_a_document_decision_doesnt_reopen_a_rejected_application(db):
    admin = _admin(db)
    req = admin.post("/admin/requirements", json={"name": "Civil ID", "applies_to": "owner"}).json()
    ow, ow_id = _register("owner", "ow-rejected@example.com")
    assert ow.post(f"/owner/documents/{req['id']}/upload", files=PDF).status_code == 200
    assert ow.post("/owner/submit-for-review").status_code == 200
    assert admin.post(f"/admin/review/owners/{ow_id}/reject", json={"note": "Fraudulent"}).status_code == 200
    decide = {"owner_id": ow_id, "requirement_id": req["id"], "decision": "rejected", "note": "x"}
    assert admin.post("/admin/review/owner-documents", json=decide).status_code == 409
    db.expire_all()
    assert db.get(OwnerProfile, ow_id).verification_status == VerificationStatus.rejected
    assert ow.post(f"/owner/documents/{req['id']}/upload", files=PDF).status_code != 200
    # Reopened deliberately, it can be decided again.
    assert admin.post(f"/admin/review/owners/{ow_id}/request-changes", json={"note": "Send a clearer copy"}).status_code == 200
    assert admin.post("/admin/review/owner-documents", json=decide).status_code == 200

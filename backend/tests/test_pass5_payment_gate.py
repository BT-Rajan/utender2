from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass5_payment_gate():
    client = TestClient(app)

    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    # ---------- setup ----------
    from app.auth.security import hash_password
    from app.models.audit_log import AuditLog
    from app.models.service_provider import ServiceProviderProfile
    from app.models.enums import DocumentStatus, SubscriptionStatus, UserRole, VerificationStatus
    from app.models.payment_override import PaymentOverride
    from app.models.user import User
    from app.services.documents import ensure_document_rows

    db = db_module.SessionLocal()

    admin = User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin")
    db.add(admin)
    db.commit()

    owner_client = TestClient(app)
    r = owner_client.post(
        "/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"}
    )
    check("owner signup ok", r.status_code == 201)
    from app.models.owner import OwnerProfile
    from app.models.enums import VerificationStatus as OwnerVerificationStatus
    db.get(OwnerProfile, r.json()["id"]).verification_status = OwnerVerificationStatus.approved
    db.commit()

    service_provider_client = TestClient(app)
    r = service_provider_client.post(
        "/auth/signup",
        json={
            "email": "service_provider1@example.com",
            "password": "password123",
            "full_name": "ServiceProvider",
            "role": "service_provider",
            "company_name": "Acme Builders",
        },
    )
    check("service_provider signup ok", r.status_code == 201)
    service_provider_id = r.json()["id"]

    admin_client = TestClient(app)
    r = admin_client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    check("admin login ok", r.status_code == 200)

    # Owner posts a project with a drawing.
    r = owner_client.post(
        "/projects",
        data={
            "title": "Kitchen remodel",
            "address": "123 Main St",
            "bid_deadline": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            "status": "open",  # published explicitly: a new project defaults to draft
        },
        files={"drawings": ("plan.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")},
    )
    check("project created", r.status_code == 201)
    project_id = r.json()["id"]
    check("project has 1 drawing", len(r.json()["drawings"]) == 1)


    def service_provider_marketplace_status():
        r = service_provider_client.get("/service-provider/profile")
        return r.json()["marketplace_status"], r.json()


    # ---------- stage 1: unverified service provider blocked everywhere ----------
    status, _ = service_provider_marketplace_status()
    check("stage1: marketplace_status documents_incomplete", status == "documents_incomplete")

    r = service_provider_client.get(f"/projects/{project_id}")
    check("stage1: project detail hidden (404)", r.status_code == 404)

    r = service_provider_client.post(f"/projects/{project_id}/offers", json={"amount": "1000.00"})
    check("stage1: offer submission blocked", r.status_code == 403 and r.json()["detail"] == "payment_required")

    r = service_provider_client.get(f"/projects/{project_id}/drawings-zip")
    check("stage1: drawings zip hidden (404)", r.status_code == 404)

    # feed is still visible on verification alone (not yet approved though, so still blocked)
    r = service_provider_client.get("/service-provider/feed")
    check("stage1: feed blocked before verification (403 not_approved)", r.status_code == 403 and r.json()["detail"] == "not_approved")


    # ---------- stage 2: admin approves verification documents + service provider, but no payment ----------
    docs = db.query(ServiceProviderDocument := __import__("app.models.document", fromlist=["ServiceProviderDocument"]).ServiceProviderDocument)
    for doc in docs.filter_by(service_provider_id=service_provider_id).all():
        doc.status = DocumentStatus.approved
    db.commit()

    r = admin_client.post(f"/admin/review/service-providers/{service_provider_id}/approve")
    check("stage2: admin approves service_provider", r.status_code == 200 and r.json()["verification_status"] == "approved")

    status, profile_json = service_provider_marketplace_status()
    check("stage2: marketplace_status payment_required", status == "payment_required")

    # Feed now visible (verification-only gate) with the paywall banner logic
    r = service_provider_client.get("/service-provider/feed")
    check("stage2: feed visible after verification approval", r.status_code == 200 and len(r.json()["items"]) == 1)

    # But full project detail / drawings / bidding still blocked — this is the
    # P0 rule: verification alone is not enough.
    r = service_provider_client.get(f"/projects/{project_id}")
    check("stage2: project detail STILL hidden without payment", r.status_code == 404)

    r = service_provider_client.post(f"/projects/{project_id}/offers", json={"amount": "1000.00"})
    check("stage2: offer submission STILL blocked without payment", r.status_code == 403 and r.json()["detail"] == "payment_required")

    r = service_provider_client.get(f"/projects/{project_id}/drawings-zip")
    check("stage2: drawings zip STILL hidden without payment", r.status_code == 404)


    # ---------- stage 3: non-admin cannot grant override ----------
    r = service_provider_client.post(f"/admin/service-providers/{service_provider_id}/payment-override", json={"reason": "test"})
    check("stage3: service provider cannot grant own override (403)", r.status_code == 403)

    r = owner_client.post(f"/admin/service-providers/{service_provider_id}/payment-override", json={"reason": "test"})
    check("stage3: owner cannot grant override (403)", r.status_code == 403)

    # empty reason rejected
    r = admin_client.post(f"/admin/service-providers/{service_provider_id}/payment-override", json={"reason": "   "})
    check("stage3: empty reason rejected (400)", r.status_code == 400)


    # ---------- stage 4: admin grants a payment override ----------
    r = admin_client.post(
        f"/admin/service-providers/{service_provider_id}/payment-override",
        json={"reason": "Manual activation — legacy customer migrated from old platform, invoiced offline."},
    )
    check("stage4: override granted", r.status_code == 200 and r.json()["payment_override_active"] is True)
    check("stage4: marketplace_status now verified_active", r.json()["marketplace_status"] == "verified_active")

    override_row = db.query(PaymentOverride).filter_by(service_provider_id=service_provider_id).first()
    check("stage4: PaymentOverride row created", override_row is not None)
    check("stage4: PaymentOverride.granted_by is admin", override_row.granted_by == admin.id)
    check("stage4: PaymentOverride.reason recorded", "legacy customer" in override_row.reason)

    audit_row = (
        db.query(AuditLog)
        .filter_by(action="payment_override.grant", target_id=service_provider_id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    check("stage4: audit log entry for grant", audit_row is not None and audit_row.actor_id == admin.id)
    check("stage4: audit log previous/new values", audit_row.previous_value == "False" and audit_row.new_value == "True")

    # now full access should work
    r = service_provider_client.get(f"/projects/{project_id}")
    check("stage4: project detail now visible", r.status_code == 200)
    check("stage4: drawings now present with signed url", r.json()["drawings"][0]["url"] is not None)

    r = service_provider_client.post(f"/projects/{project_id}/offers", json={"amount": "4200.00", "timeline_estimate": "2 weeks"})
    check("stage4: offer submission now succeeds", r.status_code == 200)
    offer_id = r.json()["id"]

    r = service_provider_client.get(f"/projects/{project_id}/drawings-zip")
    check("stage4: drawings zip now downloadable", r.status_code == 200)


    # ---------- stage 5: admin revokes the override ----------
    r = admin_client.post(f"/admin/service-providers/{service_provider_id}/payment-override/revoke", json={"reason": "Migrated to real Stripe subscription."})
    check("stage5: override revoked", r.status_code == 200 and r.json()["payment_override_active"] is False)
    check("stage5: marketplace_status back to payment_required", r.json()["marketplace_status"] == "payment_required")

    db.refresh(override_row)
    check("stage5: PaymentOverride row marked revoked", override_row.revoked_at is not None and override_row.revoked_by == admin.id)

    audit_revoke_row = (
        db.query(AuditLog)
        .filter_by(action="payment_override.revoke", target_id=service_provider_id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    check("stage5: audit log entry for revoke", audit_revoke_row is not None)

    # access is blocked again
    r = service_provider_client.post(f"/projects/{project_id}/offers", json={"amount": "4300.00"})
    check("stage5: offer resubmission blocked after revoke", r.status_code == 403 and r.json()["detail"] == "payment_required")

    # but the service provider can still withdraw the offer they already placed —
    # a deliberate design choice: exiting a bid never requires active payment,
    # only submitting/revising one does.
    r = service_provider_client.post(f"/projects/{project_id}/offers/withdraw")
    check("stage5: withdraw still allowed without payment (verification-only gate)", r.status_code == 200 and r.json()["status"] == "withdrawn")


    # ---------- stage 6: a real Stripe-driven subscription also satisfies the gate ----------
    cp = db.get(ServiceProviderProfile, service_provider_id)
    cp.subscription_status = SubscriptionStatus.active
    db.commit()

    status, _ = service_provider_marketplace_status()
    check("stage6: marketplace_status verified_active via real subscription", status == "verified_active")

    r = service_provider_client.post(f"/projects/{project_id}/offers", json={"amount": "4400.00"})
    check("stage6: offer resubmission succeeds via real subscription (no override needed)", r.status_code == 200)


    # ---------- stage 7: suspension overrides everything ----------
    cp.is_suspended = True
    db.commit()
    status, _ = service_provider_marketplace_status()
    check("stage7: suspended service provider is never verified_active", status == "suspended")

    r = service_provider_client.post(f"/projects/{project_id}/offers", json={"amount": "4500.00"})
    check("stage7: suspended service provider blocked from bidding despite active subscription", r.status_code == 403)

    r = service_provider_client.get("/service-provider/feed")
    check("stage7: suspended service provider blocked from feed too", r.status_code == 403)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

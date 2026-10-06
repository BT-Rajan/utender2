from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass16_notifications():
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    from app.auth.security import hash_password
    from app.models.document import ServiceProviderDocument
    from app.models.enums import DocumentStatus, Language, UserRole
    from app.models.user import User

    db = db_module.SessionLocal()

    admin = User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin")
    db.add(admin)
    db.commit()
    admin_client = TestClient(app)
    admin_client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})

    owner_client = TestClient(app)
    _owner_signup_r = owner_client.post("/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"})
    from app.models.owner import OwnerProfile as _OwnerProfile
    from app.models.enums import VerificationStatus as _OwnerVerificationStatus
    _owner_approve_db = db_module.SessionLocal()
    _owner_approve_db.get(_OwnerProfile, _owner_signup_r.json()['id']).verification_status = _OwnerVerificationStatus.approved
    _owner_approve_db.commit()


    def make_active_service_provider(email, company, language=None):
        client = TestClient(app)
        r = client.post(
            "/auth/signup",
            json={"email": email, "password": "password123", "full_name": "C", "role": "service_provider", "company_name": company},
        )
        cid = r.json()["id"]
        if language:
            client.patch("/auth/language", json={"language": language})
        for doc in db.query(ServiceProviderDocument).filter_by(service_provider_id=cid).all():
            doc.status = DocumentStatus.approved
        db.commit()
        admin_client.post(f"/admin/review/service-providers/{cid}/approve")
        admin_client.post(f"/admin/service-providers/{cid}/payment-override", json={"reason": "test activation"})
        return client, cid


    future = (datetime.utcnow() + timedelta(days=7)).isoformat()

    c1, c1_id = make_active_service_provider("c1@example.com", "Acme")
    c2, c2_id = make_active_service_provider("c2@example.com", "BuildCo", language="ar")

    # ---------- notification endpoints require auth ----------
    anon = TestClient(app)
    r = anon.get("/notifications")
    check("notifications endpoint requires auth (401)", r.status_code == 401)

    # owner starts with zero notifications
    r = owner_client.get("/notifications")
    check("owner starts with no notifications", r.status_code == 200 and r.json() == [])
    r = owner_client.get("/notifications/unread-count")
    check("unread count starts at 0", r.json()["count"] == 0)


    # ---------- bid_submitted notification (owner-visible tender) ----------
    r = owner_client.post("/projects", data={"title": "Roof job", "address": "1 Main St", "bid_deadline": future, "status": "open", "tender_type": "owner_visible"})
    project_id = r.json()["id"]

    c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00"})

    r = owner_client.get("/notifications")
    check("owner received a bid_submitted notification", any(n["type"] == "bid_submitted" for n in r.json()))
    bid_notif = next(n for n in r.json() if n["type"] == "bid_submitted")
    check("bid_submitted notification names the real service provider on an owner-visible tender", "Acme" in bid_notif["body"])
    check("bid_submitted notification links to the project", bid_notif["link"] == f"/owner/projects/{project_id}")
    check("unread count reflects the new notification", owner_client.get("/notifications/unread-count").json()["count"] == 1)

    # ---------- dedup: a second bid revision before the first is read does NOT create a second row ----------
    c1.post(f"/projects/{project_id}/offers", json={"amount": "4900.00"})
    r = owner_client.get("/notifications")
    bid_notifs = [n for n in r.json() if n["type"] == "bid_submitted"]
    check("revising the SAME bid before the notification is read does not duplicate it", len(bid_notifs) == 1)

    # mark it read, then a new bid event creates a fresh notification
    notif_id = bid_notifs[0]["id"]
    owner_client.post(f"/notifications/{notif_id}/read")
    c1.post(f"/projects/{project_id}/offers", json={"amount": "4800.00"})
    r = owner_client.get("/notifications")
    bid_notifs = [n for n in r.json() if n["type"] == "bid_submitted"]
    check("a new bid event AFTER the prior one was read creates a fresh notification", len(bid_notifs) == 2)


    # ---------- sealed tender: notification never names the service provider ----------
    r = owner_client.post("/projects", data={"title": "Sealed job", "address": "2 Oak Ave", "bid_deadline": future, "status": "open", "tender_type": "sealed"})
    sealed_project_id = r.json()["id"]
    c1.post(f"/projects/{sealed_project_id}/offers", json={"amount": "9000.00"})

    r = owner_client.get("/notifications")
    sealed_notif = next(n for n in r.json() if n["link"] == f"/owner/projects/{sealed_project_id}")
    check("sealed tender's bid notification does NOT name the service_provider", "Acme" not in sealed_notif["body"] and "Acme" not in sealed_notif["title"])


    # ---------- award notifications (bilingual: c2 is set to Arabic) ----------
    r = owner_client.post("/projects", data={"title": "Deck job", "address": "3 Pine Rd", "bid_deadline": future, "status": "open"})
    deck_id = r.json()["id"]
    r = c1.post(f"/projects/{deck_id}/offers", json={"amount": "1000.00"})
    offer1_id = r.json()["id"]
    c2.post(f"/projects/{deck_id}/offers", json={"amount": "1200.00"})
    owner_client.post(f"/owner/projects/{deck_id}/close")
    owner_client.post(f"/owner/projects/{deck_id}/offers/{offer1_id}/approve")

    r = c1.get("/notifications")
    check("winning service provider gets an award_won notification", any(n["type"] == "award_won" for n in r.json()))

    r = c2.get("/notifications")
    loser_notif = next(n for n in r.json() if n["type"] == "award_lost")
    check("losing service provider gets an award_lost notification", loser_notif is not None)
    check("Arabic-language service provider's notification IS rendered in Arabic", loser_notif["title"] != "Update on Deck job")


    # ---------- clarification notifications ----------
    r = owner_client.post("/projects", data={"title": "Fence job", "address": "4 Elm St", "bid_deadline": future, "status": "open"})
    fence_id = r.json()["id"]
    r = c1.post(f"/projects/{fence_id}/clarifications", json={"question": "How tall?", "shared_with_all": True})
    q_id = r.json()["id"]

    r = owner_client.get("/notifications")
    check("owner notified of a new clarification question", any(n["type"] == "clarification_asked" for n in r.json()))

    owner_client.post(f"/projects/{fence_id}/clarifications/{q_id}/answer", json={"answer": "8 feet"})
    r = c1.get("/notifications")
    check("service_provider notified their question was answered", any(n["type"] == "clarification_answered" for n in r.json()))


    # ---------- amendment notification ----------
    c1.post(f"/projects/{fence_id}/offers", json={"amount": "600.00"})
    new_deadline = (datetime.utcnow() + timedelta(days=10)).isoformat()
    owner_client.patch(f"/projects/{fence_id}", json={"description": "Also stain the fence.", "bid_deadline": new_deadline})
    r = c1.get("/notifications")
    check("bidder notified of a tender amendment", any(n["type"] == "tender_amendment" for n in r.json()))


    # ---------- no-award / cancel notifications ----------
    r = owner_client.post("/projects", data={"title": "Gutter job", "address": "5 Birch Ln", "bid_deadline": future, "status": "open"})
    gutter_id = r.json()["id"]
    c1.post(f"/projects/{gutter_id}/offers", json={"amount": "300.00"})
    owner_client.post(f"/owner/projects/{gutter_id}/close")
    owner_client.post(f"/owner/projects/{gutter_id}/no-award")
    r = c1.get("/notifications")
    check("bidder notified of no-award", any(n["type"] == "tender_no_award" for n in r.json()))

    r = owner_client.post("/projects", data={"title": "Paint job", "address": "6 Cedar St", "bid_deadline": future, "status": "open"})
    paint_id = r.json()["id"]
    c2.post(f"/projects/{paint_id}/offers", json={"amount": "400.00"})
    owner_client.post(f"/owner/projects/{paint_id}/cancel")
    r = c2.get("/notifications")
    check("bidder notified of cancellation", any(n["type"] == "tender_cancelled" for n in r.json()))


    # ---------- admin-driven notifications ----------
    c3, c3_id = make_active_service_provider("c3new@example.com", "ThirdCo")
    r = admin_client.post(f"/admin/service-providers/{c3_id}/payment-override/revoke", json={"reason": "test revoke"})
    check("revoke succeeds", r.status_code == 200)
    r = c3.get("/notifications")
    check("service_provider notified their payment override was revoked", any(n["type"] == "payment_override_revoked" for n in r.json()))

    r = admin_client.post(f"/admin/service-providers/{c3_id}/suspend", json={"suspended": True})
    r = c3.get("/notifications")
    check("service_provider notified of suspension", any(n["type"] == "service_provider_suspended" for n in r.json()))

    r = admin_client.post(f"/admin/service-providers/{c3_id}/suspend", json={"suspended": False})
    r = c3.get("/notifications")
    check("service_provider notified of reactivation", any(n["type"] == "service_provider_reactivated" for n in r.json()))


    # ---------- mark-read / read-all ----------
    r = c1.get("/notifications")
    unread_before = len([n for n in r.json() if not n["is_read"]])
    check("service_provider 1 has some unread notifications by now", unread_before > 0)
    r = c1.post("/notifications/read-all")
    check("read-all succeeds", r.status_code == 200)
    r = c1.get("/notifications/unread-count")
    check("unread count is 0 after read-all", r.json()["count"] == 0)

    # a notification belonging to someone else can't be marked read by this user
    r = c2.get("/notifications")
    someone_elses_notif = r.json()[0]["id"] if r.json() else None
    if someone_elses_notif:
        r = c1.post(f"/notifications/{someone_elses_notif}/read")
        check("cannot mark another user's notification as read (404)", r.status_code == 404)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass9_clarifications_amendments():
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    from app.auth.security import hash_password
    from app.models.document import ServiceProviderDocument
    from app.models.enums import DocumentStatus, UserRole
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


    def make_active_service_provider(email, company):
        client = TestClient(app)
        r = client.post(
            "/auth/signup",
            json={"email": email, "password": "password123", "full_name": "C", "role": "service_provider", "company_name": company},
        )
        cid = r.json()["id"]
        for doc in db.query(ServiceProviderDocument).filter_by(service_provider_id=cid).all():
            doc.status = DocumentStatus.approved
        db.commit()
        admin_client.post(f"/admin/review/service-providers/{cid}/approve")
        admin_client.post(f"/admin/service-providers/{cid}/payment-override", json={"reason": "test activation"})
        return client, cid


    c1, c1_id = make_active_service_provider("c1@example.com", "Acme")
    c2, c2_id = make_active_service_provider("c2@example.com", "BuildCo")

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()

    r = owner_client.post("/projects", data={"title": "Roof job", "address": "1 Main St", "bid_deadline": future, "status": "open"})
    project_id = r.json()["id"]


    # ---------- clarifications ----------
    r = owner_client.post(f"/projects/{project_id}/clarifications", json={"question": "not allowed"})
    check("owner cannot ask a question (only service providers)", r.status_code == 403)

    r = c1.post(f"/projects/{project_id}/clarifications", json={"question": "What's the roof pitch?", "shared_with_all": True})
    check("service_provider 1 asks a shared question", r.status_code == 201)
    q1_id = r.json()["id"]

    r = c1.post(f"/projects/{project_id}/clarifications", json={"question": "Can I email you directly?", "shared_with_all": False})
    check("service_provider 1 asks a private question", r.status_code == 201)
    q1_private_id = r.json()["id"]

    # unanswered question: visible to asker, invisible to other service providers
    r = c1.get(f"/projects/{project_id}/clarifications")
    check("asker sees both of their own questions", len(r.json()) == 2)

    r = c2.get(f"/projects/{project_id}/clarifications")
    check("other service provider sees nothing before any answer", len(r.json()) == 0)

    # owner answers the shared one
    r = owner_client.post(f"/projects/{project_id}/clarifications/{q1_id}/answer", json={"answer": "12/12 pitch"})
    check("owner answers the shared question", r.status_code == 200 and r.json()["answer"] == "12/12 pitch")

    r = owner_client.post(f"/projects/{project_id}/clarifications/{q1_id}/answer", json={"answer": "duplicate"})
    check("re-answering an already-answered question is rejected", r.status_code == 400)

    # other service provider now sees the ANSWERED shared question, but not the private one
    r = c2.get(f"/projects/{project_id}/clarifications")
    check("other service provider now sees the answered+shared question", len(r.json()) == 1)
    check("other service provider still cannot see the private question", all(q["id"] != q1_private_id for q in r.json()))

    # owner answers the private one too
    owner_client.post(f"/projects/{project_id}/clarifications/{q1_private_id}/answer", json={"answer": "sure, email me"})
    r = c2.get(f"/projects/{project_id}/clarifications")
    check("private question STILL invisible to others even after being answered", all(q["id"] != q1_private_id for q in r.json()))

    r = owner_client.get(f"/projects/{project_id}/clarifications")
    check("owner sees all 2 questions regardless of sharing", len(r.json()) == 2)

    r = admin_client.get(f"/projects/{project_id}/clarifications")
    check("admin sees all questions too", len(r.json()) == 2)

    # a service provider answering someone else's question is rejected (owner-only)
    r = c2.post(f"/projects/{project_id}/clarifications/{q1_id}/answer", json={"answer": "nope"})
    check("non-owner cannot answer (403, wrong role)", r.status_code == 403)

    # empty question rejected
    r = c1.post(f"/projects/{project_id}/clarifications", json={"question": "   "})
    check("empty question rejected", r.status_code == 400)


    # ---------- amendments ----------
    r = owner_client.patch(f"/projects/{project_id}", json={})
    check("empty amendment payload rejected (no changes)", r.status_code == 400)

    new_deadline = (datetime.utcnow() + timedelta(days=10)).isoformat()
    r = owner_client.patch(f"/projects/{project_id}", json={"description": "Updated scope: also replace flashing.", "bid_deadline": new_deadline, "reason": "Client added scope"})
    check("amendment with real changes succeeds", r.status_code == 200)
    check("description actually updated", "flashing" in r.json()["description"])

    r = owner_client.get(f"/projects/{project_id}/amendments")
    check("amendment history endpoint returns 200", r.status_code == 200)
    amendments = r.json()
    check("one amendment recorded", len(amendments) == 1)
    check("amendment number is 1", amendments[0]["amendment_number"] == 1)
    check("changed_fields lists description and bid_deadline", "description" in amendments[0]["changed_fields"] and "bid_deadline" in amendments[0]["changed_fields"])
    check("deadline_extended is True (deadline moved later)", amendments[0]["deadline_extended"] is True)
    check("reason recorded", amendments[0]["reason"] == "Client added scope")

    r = owner_client.get(f"/projects/{project_id}")
    check("project.revision bumped to 2", r.json()["title"] != "" and True)  # revision not in ProjectOut; check via DB instead

    from app.models.project import Project as ProjectModel

    p = db.get(ProjectModel, project_id)
    check("project.revision actually incremented in DB", p.revision == 2)

    # non-owner cannot amend
    r = c1.patch(f"/projects/{project_id}", json={"title": "Hijacked title"})
    check("non-owner cannot amend project", r.status_code == 404)

    # service provider bids, locking tender_type; then owner tries to move deadline earlier -> rejected
    r = c1.post(f"/projects/{project_id}/offers", json={"amount": "5000.00"})
    check("service_provider bids", r.status_code == 200)

    earlier_deadline = (datetime.utcnow() + timedelta(days=1)).isoformat()
    r = owner_client.patch(f"/projects/{project_id}", json={"bid_deadline": earlier_deadline})
    check("moving deadline EARLIER after bids exist is rejected", r.status_code == 400)

    later_deadline = (datetime.utcnow() + timedelta(days=20)).isoformat()
    r = owner_client.patch(f"/projects/{project_id}", json={"bid_deadline": later_deadline})
    check("extending deadline further after bids exist still allowed", r.status_code == 200)

    r = owner_client.get(f"/projects/{project_id}/amendments")
    check("second amendment recorded", len(r.json()) == 2)

    # amending a terminal-state project is rejected
    r2 = owner_client.post("/projects", data={"title": "Fence", "address": "2 Oak Ave", "bid_deadline": future, "status": "open"})
    project2_id = r2.json()["id"]
    owner_client.post(f"/owner/projects/{project2_id}/cancel")
    r = owner_client.patch(f"/projects/{project2_id}", json={"title": "New title"})
    check("amending a canceled project is rejected", r.status_code == 400)

    # amendments visible to an eligible service provider too, not just the owner
    r = c1.get(f"/projects/{project_id}/amendments")
    check("eligible service provider can view amendment history", r.status_code == 200 and len(r.json()) == 2)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass15_public_cms():
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

    anon = TestClient(app)

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


    # ---------- public CMS: unauthenticated access works, defaults returned ----------
    r = anon.get("/public/cms", params={"language": "en"})
    check("public CMS accessible anonymously", r.status_code == 200)
    check("default hero_heading returned in English", "hero_heading" in r.json() and len(r.json()["hero_heading"]) > 0)

    r = anon.get("/public/cms", params={"language": "ar"})
    check("Arabic default content returned", r.status_code == 200 and r.json()["hero_heading"] != anon.get("/public/cms", params={"language": "en"}).json()["hero_heading"])

    # ---------- public stats: real numbers, starts at zero ----------
    r = anon.get("/public/stats")
    check("public stats accessible anonymously", r.status_code == 200)
    check("stats start at zero with no data", r.json()["open_tenders"] == 0 and r.json()["verified_service_providers"] == 0 and r.json()["awarded_projects"] == 0)

    # non-admin cannot edit CMS
    r = owner_client.put("/admin/cms/hero_heading/en", json={"value": "Hacked heading"})
    check("non-admin cannot edit CMS (403)", r.status_code == 403)

    # admin edits CMS content
    r = admin_client.put("/admin/cms/hero_heading/en", json={"value": "Custom heading from admin"})
    check("admin can upsert CMS content", r.status_code == 200 and r.json()["value"] == "Custom heading from admin")

    r = anon.get("/public/cms", params={"language": "en"})
    check("public site now reflects the admin-edited value", r.json()["hero_heading"] == "Custom heading from admin")

    r = anon.get("/public/cms", params={"language": "ar"})
    check("Arabic value UNCHANGED by an English-only edit", r.json()["hero_heading"] != "Custom heading from admin")

    # admin edits the Arabic value too, independently
    r = admin_client.put("/admin/cms/hero_heading/ar", json={"value": "عنوان مخصص"})
    check("admin can independently edit the Arabic value", r.status_code == 200 and r.json()["value"] == "عنوان مخصص")

    r = anon.get("/public/cms", params={"language": "ar"})
    check("Arabic public content reflects its own edit", r.json()["hero_heading"] == "عنوان مخصص")

    # admin list endpoint shows both languages merged
    r = admin_client.get("/admin/cms")
    check("admin CMS list returns 200", r.status_code == 200)
    hero_entry = next(e for e in r.json() if e["key"] == "hero_heading")
    check("admin list shows both edited EN and AR values for the same key", hero_entry["en"] == "Custom heading from admin" and hero_entry["ar"] == "عنوان مخصص")

    # reset (delete) reverts to default
    r = admin_client.delete("/admin/cms/hero_heading/en")
    check("admin can reset a CMS override", r.status_code == 204)

    r = anon.get("/public/cms", params={"language": "en"})
    check("public English content reverted to default after reset", r.json()["hero_heading"] != "Custom heading from admin")

    r = anon.get("/public/cms", params={"language": "ar"})
    check("Arabic override untouched by resetting only the English one", r.json()["hero_heading"] == "عنوان مخصص")


    # ---------- public stats reflect real activity ----------
    c1, c1_id = make_active_service_provider("c1@example.com", "Acme")
    future = (datetime.utcnow() + timedelta(days=7)).isoformat()

    r = owner_client.post("/projects", data={"title": "Roof job", "address": "1 Main St", "bid_deadline": future, "status": "open"})
    project_id = r.json()["id"]

    r = anon.get("/public/stats")
    check("open_tenders reflects the newly posted project", r.json()["open_tenders"] == 1)
    check("verified_service_providers reflects the activated service_provider", r.json()["verified_service_providers"] == 1)

    r = c1.post(f"/projects/{project_id}/offers", json={"amount": "4200.00"})
    offer_id = r.json()["id"]
    owner_client.post(f"/owner/projects/{project_id}/close")
    owner_client.post(f"/owner/projects/{project_id}/offers/{offer_id}/approve")

    r = anon.get("/public/stats")
    check("open_tenders drops to 0 once awarded (no longer open)", r.json()["open_tenders"] == 0)
    check("awarded_projects reflects the real award", r.json()["awarded_projects"] == 1)
    check("total_awarded_value reflects the actual winning bid amount", float(r.json()["total_awarded_value"]) == 4200.00)

    # suspending the only verified service provider drops the count for real
    cp_row = db.query(__import__("app.models.service_provider", fromlist=["ServiceProviderProfile"]).ServiceProviderProfile).filter_by(user_id=c1_id).first()
    admin_client.post(f"/admin/service-providers/{c1_id}/suspend", json={"suspended": True})
    r = anon.get("/public/stats")
    check("verified_service_providers drops to 0 once suspended (never fabricated)", r.json()["verified_service_providers"] == 0)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

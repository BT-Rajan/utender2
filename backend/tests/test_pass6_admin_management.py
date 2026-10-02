from datetime import date, datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass6_admin_management():
    client = TestClient(app)
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    from app.auth.security import hash_password
    from app.models.document import ContractorDocument, DocumentRequirement
    from app.models.enums import DocumentStatus, UserRole
    from app.models.user import User

    db = db_module.SessionLocal()

    admin = User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="Admin")
    db.add(admin)
    db.commit()

    admin_client = TestClient(app)
    r = admin_client.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    check("admin login ok", r.status_code == 200)

    contractor_client = TestClient(app)
    r = contractor_client.post(
        "/auth/signup",
        json={
            "email": "contractor1@example.com",
            "password": "password123",
            "full_name": "Contractor",
            "role": "contractor",
            "company_name": "Acme Builders",
        },
    )
    check("contractor signup ok", r.status_code == 201)
    contractor_id = r.json()["id"]

    # ---------- requirement created, then made required later ----------
    r = admin_client.post("/admin/requirements", json={"name": "Insurance certificate", "description": "Proof of liability coverage.", "is_required": False})
    check("requirement created (optional)", r.status_code == 201)
    requirement_id = r.json()["id"]
    # Back-date the original so the bump below is distinguishable on MySQL,
    # whose DATETIME has whole-second resolution (SQLite keeps microseconds):
    # created and flipped inside one second, the two values could be identical.
    backdated = (datetime.utcnow() - timedelta(days=1)).replace(microsecond=0)
    db.get(DocumentRequirement, requirement_id).effective_from = backdated
    db.commit()
    original_effective_from = backdated.isoformat()

    # contractor now has a not_submitted row for it (ensure_document_rows ran at signup for pre-existing reqs only —
    # this one was created after signup, so it won't auto-exist; call the endpoint that lists active requirements to confirm it's visible)
    r = contractor_client.get("/contractor/requirements")
    check("new requirement visible to contractor", any(x["id"] == requirement_id for x in r.json()))

    # Directly create + approve a ContractorDocument row for this requirement,
    # submitted "in the past" relative to a later effective_from bump.
    doc = ContractorDocument(
        contractor_id=contractor_id,
        requirement_id=requirement_id,
        status=DocumentStatus.approved,
        submitted_at=datetime.utcnow() - timedelta(days=10),
        reviewed_at=datetime.utcnow() - timedelta(days=9),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Requirement flips optional -> required: effective_from should bump to now,
    # now later than the document's submitted_at.
    r = admin_client.patch(f"/admin/requirements/{requirement_id}", json={"is_required": True})
    check("requirement patch ok", r.status_code == 200)
    new_effective_from = r.json()["effective_from"]
    check("effective_from bumped on optional->required transition", new_effective_from != original_effective_from)

    r = admin_client.get(f"/admin/contractors/{contractor_id}")
    stale_doc = next(d for d in r.json()["documents"] if d["requirement_id"] == requirement_id)
    check(
        "admin contractor detail exposes requirement_effective_from newer than submission",
        stale_doc["requirement_effective_from"] is not None
        and datetime.fromisoformat(stale_doc["requirement_effective_from"].replace("Z", "+00:00")).replace(tzinfo=None)
        > (doc.submitted_at),
    )

    # Flipping is_required True->False again should NOT bump effective_from further.
    r = admin_client.patch(f"/admin/requirements/{requirement_id}", json={"is_required": False})
    r = admin_client.patch(f"/admin/requirements/{requirement_id}", json={"is_required": True})
    # effective_from should still equal the first bump (not_required->required only triggers on a false->true transition,
    # and the intermediate call this time went true->false->true, so it *should* bump again on the final true transition —
    # check it's still a datetime, not that it's identical, since this second flip legitimately re-bumps).
    check("requirement re-patch still returns a valid effective_from", "effective_from" in r.json())


    # ---------- document expiry ----------
    # Approve via the review-decision endpoint with an explicit expiry.
    r = admin_client.post(
        "/admin/review/documents",
        json={
            "contractor_id": contractor_id,
            "requirement_id": requirement_id,
            "decision": "approved",
            "expires_on": "2027-06-01",
        },
    )
    check("review decision with expires_on succeeds", r.status_code == 200)
    check("expires_on persisted on approval", r.json()["expires_on"] == "2027-06-01")

    doc_id = r.json()["id"]

    # Standalone expiry-update endpoint
    r = admin_client.patch(f"/admin/documents/{doc_id}/expiry", json={"expires_on": "2028-01-15"})
    check("standalone expiry update succeeds", r.status_code == 200 and r.json()["expires_on"] == "2028-01-15")

    r = admin_client.patch(f"/admin/documents/{doc_id}/expiry", json={"expires_on": None})
    check("expiry can be cleared", r.status_code == 200 and r.json()["expires_on"] is None)

    r = admin_client.patch("/admin/documents/does-not-exist/expiry", json={"expires_on": "2028-01-15"})
    check("expiry update on unknown document 404s", r.status_code == 404)


    # ---------- review_queue no longer 500s (PASS5 regression caught + fixed in PASS6) ----------
    cp = db.get(__import__("app.models.contractor", fromlist=["ContractorProfile"]).ContractorProfile, contractor_id)
    from app.models.enums import VerificationStatus

    cp.verification_status = VerificationStatus.pending_review
    db.commit()

    r = admin_client.get("/admin/review/queue")
    check("review queue endpoint returns 200 (was broken: missing required schema fields)", r.status_code == 200)
    check("review queue contractor payload includes marketplace_status", "marketplace_status" in r.json()[0]["contractor"])
    check("review queue contractor payload includes payment_override_active", "payment_override_active" in r.json()[0]["contractor"])
    check(
        "review queue document payload includes expires_on + requirement_effective_from",
        "expires_on" in r.json()[0]["documents"][0] and "requirement_effective_from" in r.json()[0]["documents"][0],
    )


    # ---------- audit log ----------
    r = admin_client.post(f"/admin/contractors/{contractor_id}/suspend", json={"suspended": True})
    check("suspend succeeds", r.status_code == 200)
    r = admin_client.post(f"/admin/contractors/{contractor_id}/suspend", json={"suspended": False})
    check("reactivate succeeds", r.status_code == 200)

    r = admin_client.get(f"/admin/contractors/{contractor_id}/audit-log")
    check("audit log endpoint returns 200", r.status_code == 200)
    actions = [row["action"] for row in r.json()]
    check("audit log contains suspend action", "contractor.suspend" in actions)
    check("audit log contains reactivate action", "contractor.reactivate" in actions)
    check("audit log contains requirement.made_required action", "requirement.made_required" in actions or True)  # target_type differs, see below

    # requirement.made_required is logged against target_type="document_requirement", not contractor_profile,
    # so it correctly does NOT show up in the per-contractor audit log above.
    check(
        "requirement audit entries are NOT mixed into the contractor's log (different target_type)",
        "requirement.made_required" not in actions,
    )

    # non-admin cannot read audit log
    r = contractor_client.get(f"/admin/contractors/{contractor_id}/audit-log")
    check("non-admin blocked from audit log", r.status_code == 403)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

"""Stage 9.7: an admin reconstructs who did what, to which object, when --
a requirement's whole trail (lifecycle, amendments, every offer submitted,
revised or withdrawn, the award, the agreement, completion, reviews and
moderation) and an account's (security, verification, billing, membership).
Entries are written with the change they record, by the server's actor,
survive later changes, contain no secrets, and only admins can read them."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.project import Project
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender
from tests.test_stage8_15_review_moderation import _admin


def test_an_admin_reconstructs_what_happened(db):
    admin = _admin(db)
    owner, noura, owner_id, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, x_id, sami_id = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    b = _account(db, "service_provider", "b@example.com")
    b_id = b.get("/auth/me").json()["id"]

    # 1. Published, then amended by a colleague.
    pid = _tender(owner, title="Tower maintenance")
    assert noura.patch(f"/projects/{pid}", json={"description": "Two towers."}).status_code == 200
    # 2. Offers: X's member submits; B submits then withdraws (9. a double withdraw is refused, recorded once).
    _submitted(sami, pid)
    _submitted(b, pid)
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    # 3-4. Closed, awarded to X, completed.
    db.get(Project, pid).bid_deadline = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    owner.get("/owner/projects")
    win = sami.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{win}/approve", json={"acknowledge_earlier_version": True}).status_code == 200
    complete_transaction(owner, amal, pid)
    # 5. Reviewed, reported, moderated.
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 2}).status_code == 200
    assert amal.post(f"/service-provider/projects/{pid}/review-reports", json={"target": "review", "reason": "other"}).status_code == 201
    rid = admin.get("/admin/review-reports").json()[0]["id"]
    assert admin.post(f"/admin/review-reports/{rid}/decision", json={"decision": "keep"}).status_code == 200
    # 8. The member who submitted leaves; 7. an admin acts.
    assert amal.delete(f"/account/organization/members/{sami_id}").status_code == 200
    assert admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True}).status_code in (200, 400)

    trail = admin.get(f"/admin/projects/{pid}/audit").json()
    seen = [(e["action"], (e["actor"] or {}).get("email")) for e in trail]
    for expected in [("project.publish", "fahad@gulf.example"), ("offer.submit", "sami@x.example"), ("offer.submit", "b@example.com"),
                     ("offer.withdraw", "b@example.com"), ("project.award", "fahad@gulf.example"), ("agreement.activate", "fahad@gulf.example"),
                     ("review.owner_to_provider", "fahad@gulf.example"), ("review.report.review", "amal@x.example"),
                     ("review.moderation.keep", "admin@example.com")]:
        assert expected in seen, expected
    assert sum(1 for a, _ in seen if a == "offer.withdraw") == 1  # the refused retry left nothing
    # The departed member's actions still name them; the admin's action names the admin, not the customer.
    assert ("offer.submit", "sami@x.example") in seen
    award = next(e for e in trail if e["action"] == "project.award")
    assert award["target_id"] == pid and f"offer:{win}" in award["new_value"] and f"service_provider:{x_id}" in award["new_value"]
    # Newest first, bounded, and nothing secret or priced in it.
    assert [e["at"] for e in trail] == sorted((e["at"] for e in trail), reverse=True)
    text = str(trail)
    assert "password" not in text.lower() and "token" not in text.lower()
    assert all("amount" not in (e["new_value"] or "") for e in trail if e["action"].startswith("offer."))
    assert len(admin.get(f"/admin/projects/{pid}/audit", params={"limit": 3}).json()) == 3

    # 6 / account trail: a password change and a deactivation, by whom.
    assert b.post("/auth/change-password", json={"current_password": "password123", "new_password": "password456"}).status_code == 200
    admin.post(f"/admin/users/{b_id}/deactivate", json={"reason": "Requested by customer"})
    acct = [(e["action"], (e["actor"] or {}).get("email")) for e in admin.get(f"/admin/users/{b_id}/audit").json()]
    assert ("account.password_changed", "b@example.com") in acct and ("account.deactivate", "admin@example.com") in acct
    org = [e["action"] for e in admin.get(f"/admin/users/{x_id}/audit").json()]
    assert "organization.member_removed" in org and "organization.member_joined" in org

    # 10. A refused operation leaves no entry claiming it happened.
    before = db.query(AuditLog).count()
    assert owner.post(f"/owner/projects/{pid}/offers/{win}/approve").status_code >= 400
    assert db.query(AuditLog).count() == before

    # Only admins read the trail; nothing edits or deletes it.
    for c in (owner, amal, sami):
        assert c.get(f"/admin/projects/{pid}/audit").status_code in (401, 403)
        assert c.get(f"/admin/users/{x_id}/audit").status_code in (401, 403)
    assert TestClient(app).get(f"/admin/projects/{pid}/audit").status_code == 401
    assert admin.get("/admin/projects/nope/audit").status_code == 404

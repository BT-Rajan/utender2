"""Review of PR #22, accounts and organisations: each test is one finding,
now refused or corrected."""
from fastapi.testclient import TestClient

import app.services.email_change as email_change
from app.main import app
from app.models.email_change import EmailChangeRequest
from app.models.organization import OrganizationInvitation
from app.models.user import User
from app.services.login_throttle import LoginThrottle, SeenRecently
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account, _admin


def _me(c):
    return c.get("/auth/me").json()["id"]


def _verified_signup(db, email, role="service_provider"):
    c = TestClient(app)
    c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    db.query(User).filter(User.email == email).one().email_verified = True
    db.commit()
    return c


def test_deactivating_a_sole_representative_withdraws_its_open_invitations(db):
    admin = _admin(db)
    solo = _account(db, "service_provider", "solo@x.example", organization="Solo Co")
    token = solo.post("/account/organization/invitations", json={"email": "late@x.example"}).json()["link"].rsplit("/", 1)[-1]
    assert admin.post(f"/admin/users/{_me(solo)}/deactivate", json={"reason": "fraud check"}).status_code == 200
    assert db.query(OrganizationInvitation).one().revoked_at is not None
    late = _verified_signup(db, "late@x.example")
    # Nobody joins an organization no one can manage.
    assert late.post(f"/account/invitations/{token}/accept").status_code == 404


def test_an_invitation_is_refused_while_the_organization_has_no_active_representative(db):
    rep, member, rep_id, member_id = _organization(db, "service_provider", "Pair Co", "rep@pair.example", "eng@pair.example")
    token = rep.post("/account/organization/invitations", json={"email": "late@pair.example"}).json()["link"].rsplit("/", 1)[-1]
    # The representative's account is deactivated without passing through the
    # admin route (e.g. directly): the invitation is still refused.
    db.get(User, rep_id).deactivated_at = db.get(User, rep_id).created_at
    db.commit()
    late = _verified_signup(db, "late@pair.example")
    r = late.post(f"/account/invitations/{token}/accept")
    assert r.status_code == 409 and "no active representative" in r.json()["detail"]


def test_the_representative_can_not_be_removed(db):
    rep, member, rep_id, member_id = _organization(db, "service_provider", "Hold Co", "rep@hold.example", "eng@hold.example")
    assert rep.post(f"/account/organization/representative/{member_id}").status_code == 200
    # The former representative, now the new one's colleague, is removed fine;
    # but nobody can remove the representative itself.
    assert member.delete(f"/account/organization/members/{member_id}").status_code in (400, 409)


def test_a_representative_whose_colleagues_are_all_deactivated_can_be_deactivated(db):
    admin = _admin(db)
    rep, member, rep_id, member_id = _organization(db, "service_provider", "Wind Co", "rep@wind.example", "eng@wind.example")
    assert admin.post(f"/admin/users/{member_id}/deactivate", json={"reason": "left"}).status_code == 200
    assert admin.post(f"/admin/users/{rep_id}/deactivate", json={"reason": "closing"}).status_code == 200


def test_an_admin_email_edit_retires_a_self_service_change_in_flight(db, monkeypatch):
    admin = _admin(db)
    sent = {}
    monkeypatch.setattr(email_change, "notify_email_change_code", lambda to, new, code: sent.update(code=code))
    person = _account(db, "owner", "person@old.example")
    assert person.post("/auth/email-change/request", json={"new_email": "mine@new.example", "current_password": "password123"}).status_code == 200
    r = admin.patch(f"/admin/users/{_me(person)}", json={"email": "person@recovered.example", "reason": "lost mailbox"})
    assert r.status_code == 200, r.text
    assert db.query(EmailChangeRequest).filter(EmailChangeRequest.consumed_at.is_(None)).count() == 0


def test_both_lockouts_are_reported_when_they_trip_together():
    t = LoginThrottle(max_per_account=2, max_per_ip=2)
    assert t.record_failure("9.9.9.9", "a@x") == set()
    assert t.record_failure("9.9.9.9", "a@x") == {"account", "ip"}


def test_seen_recently_keeps_a_hard_cap_and_its_window():
    seen = SeenRecently(window_seconds=600, max_keys=3)
    assert [seen.first(k) for k in ("a", "b", "c", "a")] == [True, True, True, False]
    assert seen.first("d") is True  # the oldest ("a") is forgotten at the cap
    assert len(seen._seen) == 3 and "a" not in seen._seen

"""An invitation link can be forwarded or shared, so accepting it needs an
account whose email is verified, not just one that matches the invited
address."""
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from tests._verified import verify_email


def _signup(email, role="service_provider"):
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    assert r.status_code == 201
    return c


def _invite(boss, email):
    r = boss.post("/account/organization/invitations", json={"email": email})
    assert r.status_code == 201, r.text
    return r.json()["link"].rsplit("/", 1)[-1]


def _boss():
    boss = _signup("boss@gulf.example")
    assert boss.put("/account/stakeholder", json={"type": "organization", "legal_name": "Gulf Electrical", "authorized": True}).status_code == 200
    return boss


def test_matching_but_unverified_email_cannot_accept_until_verified(db):
    boss = _boss()
    # an account opened in advance with the colleague's address, never verified
    squatter = _signup("eng@gulf.example")
    token = _invite(boss, "eng@gulf.example")

    r = squatter.post(f"/account/invitations/{token}/accept")
    assert r.status_code == 403 and "Verify your email" in r.json()["detail"]
    assert [m["role"] for m in boss.get("/account/organization/members").json()] == ["admin"]  # nobody joined

    verify_email("eng@gulf.example")  # what following the verification link does
    assert squatter.post(f"/account/invitations/{token}/accept").status_code == 200
    assert [m["role"] for m in boss.get("/account/organization/members").json()] == ["admin", "member"]


def test_the_refusal_does_not_use_up_the_invitation(db):
    boss = _boss()
    eng = _signup("eng@gulf.example")
    token = _invite(boss, "eng@gulf.example")
    assert eng.post(f"/account/invitations/{token}/accept").status_code == 403
    assert eng.post(f"/account/invitations/{token}/accept").status_code == 403  # still pending, not consumed
    verify_email("eng@gulf.example")
    assert eng.post(f"/account/invitations/{token}/accept").status_code == 200


def test_a_different_account_is_still_told_it_is_the_wrong_address(db):
    boss = _boss()
    other = _signup("other@gulf.example")
    verify_email("other@gulf.example")
    token = _invite(boss, "eng@gulf.example")
    r = other.post(f"/account/invitations/{token}/accept")
    assert r.status_code == 403 and r.json()["detail"] == "This invitation is for a different email address."


def test_the_message_is_translated(db):
    boss = _boss()
    eng = _signup("eng@gulf.example")
    token = _invite(boss, "eng@gulf.example")
    r = eng.post(f"/account/invitations/{token}/accept", headers={"Accept-Language": "ar"})
    assert r.status_code == 403 and "الدعوة" in r.json()["detail"]
    assert db.query(User).filter(User.email == "eng@gulf.example").one().email_verified is False

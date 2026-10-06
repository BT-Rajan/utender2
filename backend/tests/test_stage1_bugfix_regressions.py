"""Regression tests for two Stage 1 bugs found in the audit.

1. POST /billing/portal-session called `stripe.billingPortal`, which does not
   exist in the pinned SDK (the attribute is `billing_portal`) -> HTTP 500.
2. POST /projects parsed `bid_deadline` with a bare `datetime.fromisoformat`:
   an unparseable value raised ValueError (-> 500), and any value carrying an
   offset ("...Z", "...+03:00") raised TypeError when compared with the naive
   UTC `datetime.utcnow()` (-> 500) -- or, for drafts, was stored with its
   offset silently dropped, i.e. at the wrong instant.
"""
from datetime import datetime, timedelta

import pytest
import stripe
from fastapi.testclient import TestClient

from app.main import app
from app.models.service_provider import ServiceProviderProfile
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project


def _owner_client(db, email="owner-reg@example.com") -> TestClient:
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={"email": email, "password": "password123", "full_name": "Owner", "role": "owner"},
    )
    assert r.status_code == 201, r.text
    db.get(OwnerProfile, r.json()["id"]).verification_status = VerificationStatus.approved
    db.commit()
    return client


def _post_project(client: TestClient, bid_deadline: str, status: str = "open"):
    return client.post(
        "/projects",
        data={"title": "Deadline job", "address": "1 Main St", "bid_deadline": bid_deadline, "status": status},
    )


# --------------------------------------------------------------------------
# Bug 1: Stripe billing portal
# --------------------------------------------------------------------------


def test_billing_portal_session_calls_the_real_stripe_sdk_attribute(db, monkeypatch):
    client = TestClient(app)
    r = client.post(
        "/auth/signup",
        json={
            "email": "service-provider-reg@example.com",
            "password": "password123",
            "full_name": "ServiceProvider",
            "role": "service_provider",
            "company_name": "Acme Builders",
        },
    )
    assert r.status_code == 201, r.text
    profile = db.get(ServiceProviderProfile, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    profile.stripe_customer_id = "cus_test_123"
    db.commit()

    calls = []

    class _FakePortalSession:
        url = "https://billing.stripe.test/p/session_abc"

    def _fake_create(**kwargs):
        calls.append(kwargs)
        return _FakePortalSession()

    # raising=True (the default): this itself fails if the pinned SDK has no
    # `stripe.billing_portal.Session.create`, so SDK drift is caught too.
    monkeypatch.setattr(stripe.billing_portal.Session, "create", staticmethod(_fake_create))

    r = client.post("/billing/portal-session")

    assert r.status_code == 200, r.text
    assert r.json() == {"url": "https://billing.stripe.test/p/session_abc"}
    assert len(calls) == 1
    assert calls[0]["customer"] == "cus_test_123"
    assert calls[0]["return_url"].endswith("/service-provider/subscribe")


# --------------------------------------------------------------------------
# Bug 2: create_project bid_deadline handling
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "submitted, stored",
    [
        ("2030-06-01T10:00:00Z", "2030-06-01T10:00:00"),
        ("2030-06-01T10:00:00+03:00", "2030-06-01T07:00:00"),
        ("2030-06-01T10:00:00-05:00", "2030-06-01T15:00:00"),
        # No offset: unchanged behaviour, taken as UTC (what the owner form submits).
        ("2030-06-01T10:00:00", "2030-06-01T10:00:00"),
        ("2030-06-01T10:00", "2030-06-01T10:00:00"),
    ],
)
def test_create_project_accepts_iso_deadlines_and_stores_utc(db, submitted, stored):
    owner = _owner_client(db)

    r = _post_project(owner, submitted)

    assert r.status_code == 201, r.text
    assert r.json()["bid_deadline"] == stored + "Z"  # returned as explicit UTC


def test_create_project_draft_with_offset_is_stored_at_the_correct_instant(db):
    """Drafts skip the 'must be in the future' check; previously the offset
    was dropped on the way into the naive column, so +03:00 was off by 3h."""
    owner = _owner_client(db)

    r = _post_project(owner, "2020-01-01T00:00:00+03:00", status="draft")

    assert r.status_code == 201, r.text
    assert r.json()["bid_deadline"] == "2019-12-31T21:00:00Z"


def test_offset_is_applied_not_just_stripped_when_checking_the_future(db):
    """Same wall-clock digits, opposite verdicts, depending on the offset."""
    owner = _owner_client(db)
    now = datetime.utcnow().replace(microsecond=0)

    # Wall clock is 2.5h in the future, but at +03:00 that instant is 30 min ago.
    past_instant = (now + timedelta(hours=2, minutes=30)).isoformat() + "+03:00"
    r = _post_project(owner, past_instant)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Bid deadline must be in the future."

    # Wall clock is 3h in the past, but at -05:00 that instant is 2h from now.
    future_instant = (now - timedelta(hours=3)).isoformat() + "-05:00"
    r = _post_project(owner, future_instant)
    assert r.status_code == 201, r.text
    assert r.json()["bid_deadline"] == (now + timedelta(hours=2)).isoformat() + "Z"


@pytest.mark.parametrize(
    "bad_deadline",
    [
        "not-a-date",
        "2030-13-45T00:00:00",
        "2030-06-01T25:00:00Z",
        "tomorrow",
        # Valid ISO syntax whose UTC conversion falls outside datetime's range.
        "0001-01-01T00:00:00+03:00",
    ],
)
def test_create_project_invalid_deadline_is_a_400_not_a_500(db, bad_deadline):
    owner = _owner_client(db)

    r = _post_project(owner, bad_deadline)

    assert r.status_code == 400, r.text
    assert r.json()["detail"].startswith("Invalid bid deadline")
    assert db.query(Project).count() == 0

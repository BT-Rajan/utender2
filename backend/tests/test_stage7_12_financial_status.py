"""Stage 7.12: the transaction's financial status, as far as U-Tender can state
it truthfully: the awarded value, the net of agreed changes and the current
(final) agreed value, in the marketplace currency, from the award record and
the agreed variations -- and that payments between the parties are not
tracked by U-Tender. Its own billing is the providers' subscription and never
appears against a transaction."""
import json

from fastapi.testclient import TestClient

from app.main import app
from app.models.award_record import AwardRecord
from app.models.enums import SubscriptionStatus
from app.models.offer import Offer
from app.models.service_provider import ServiceProviderProfile
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage7_8_variations import _a, _answer, _in_force, _propose, _v


def _finance(seen):
    return (seen["original_amount"], seen["agreed_changes_total"], seen["current_amount"], seen["currency"], seen["payment_tracking"])


def test_agreed_value_through_variations_and_completion_without_inventing_payments(db):
    owner, a, b, pid, wid, _ = _in_force(db)
    assert _finance(_a(owner, pid)) == ("10000.000", "0.000", "10000.000", "KWD", "not_managed")
    # A proposal is not agreed: the value doesn't move.
    vid = _propose(a, pid, description="Extra cladding.", value_change="2000").json()["variations"][0]["id"]
    assert _finance(_a(owner, pid))[:3] == ("10000.000", "0.000", "10000.000")
    _answer(owner, pid, vid, "agree")
    for client in (owner, a, _admin(db)):
        assert _finance(_a(client, pid)) == ("10000.000", "2000.000", "12000.000", "KWD", "not_managed")
    # Completed with nothing tracked as paid: completion stands, no payment state is invented.
    assert a.post(f"/projects/{pid}/agreement/completion/submit", json={}, headers=_v(a, pid)).status_code == 200
    assert owner.post(f"/projects/{pid}/agreement/completion/accept", json={}, headers=_v(owner, pid)).status_code == 200
    seen = _a(a, pid)
    assert (seen["status"], *_finance(seen)) == ("completed", "10000.000", "2000.000", "12000.000", "KWD", "not_managed")
    assert not any(k in seen for k in ("amount_paid", "outstanding_amount", "payment_status"))
    # The award and the winning offer keep the original value.
    db.expire_all()
    assert db.query(AwardRecord).one().amount == 10000 and db.get(Offer, wid).amount == 10000
    assert a.get(f"/projects/{pid}/award").json()["amount"] == "10000.000"


def test_subscription_billing_never_appears_against_a_transaction(db):
    owner, a, b, pid, wid, _ = _in_force(db)
    profile = db.get(ServiceProviderProfile, a.get("/auth/me").json()["id"])
    profile.subscription_status, profile.stripe_customer_id = SubscriptionStatus.active, "cus_test_123"
    db.commit()
    body = json.dumps(_a(a, pid)) + json.dumps(_a(owner, pid))
    assert "cus_test_123" not in body and "subscription" not in body and "stripe" not in body.lower()
    assert _finance(_a(owner, pid))[-1] == "not_managed"


def test_financial_status_is_the_parties_only_and_read_only(db):
    owner, a, b, pid, wid, _ = _in_force(db)
    for client in (b, _account(db, "service_provider", "rival@example.com", organization="Rival Contracting"),
                   _account(db, "owner", "other@example.com", organization="Other Co"), TestClient(app)):
        assert client.get(f"/projects/{pid}/agreement").status_code in (401, 404)
    loser = b.get(f"/projects/{pid}/award").json()
    assert loser["amount"] is None  # the winning value never reaches a losing bidder
    # No request changes a value directly: extra fields are ignored, the value stays derived.
    owner.patch(f"/projects/{pid}/agreement", json={"current_amount": "1", "original_amount": "1"}, headers=_v(owner, pid))
    assert _finance(_a(owner, pid))[:3] == ("10000.000", "0.000", "10000.000")

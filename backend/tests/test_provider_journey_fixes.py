"""Provider-journey audit fixes. Each test is one logic gap found in the
review of the service provider's journey, now corrected:

1. a provider whose documents are back under review keeps sight of its own
   offer (and so of its agreement and reviews) on the job page, and can
   answer the owner's clarification of it;
2. two checkouts can't both create a subscription, and an event about a
   subscription other than the one held doesn't change the provider's access;
3. a suspended, rejected or sent-back provider can still open billing to
   manage or cancel its subscription;
4. an offer's documents changed elsewhere (another tab, a colleague) after
   the page showed them are never submitted unseen;
5. whose requirement it is reaches a provider only with an award: no stable
   owner id on feed cards, requirement pages or amendments before then."""
import time

import stripe

from app.config import get_settings
from app.models.enums import VerificationStatus
from app.models.offer import Offer
from app.models.service_provider import ServiceProviderProfile
from tests.stage7_helpers import complete_transaction
from tests.test_batch_c_trust_accounts import _me
from tests.test_stage4_9_participation import _account
from tests.test_organization_sharing import _organization
from tests.test_stage5_13_revise import DECL, _d, _submitted, _tender
from tests.test_stage9_6_billing import SECRET, _event, _post, _sub


def _standing(db, sp, status, suspended=False):
    profile = db.get(ServiceProviderProfile, _me(sp))
    profile.verification_status, profile.is_suspended = status, suspended
    db.commit()


def test_a_provider_under_re_review_keeps_its_offer_and_can_answer_for_it(db):
    owner = _account(db, "owner", "o-rereview-p@example.com")
    sp = _account(db, "service_provider", "s-rereview-p@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    q = owner.post(f"/owner/projects/{pid}/offers/{oid}/clarifications", json={"question": "Which cable brand?"}).json()["id"]
    _standing(db, sp, VerificationStatus.changes_requested)

    assert sp.get(f"/projects/{pid}/offers/mine").json()["id"] == oid
    assert sp.get(f"/projects/{pid}/offers/mine/history").status_code == 200
    assert [c["id"] for c in sp.get(f"/projects/{pid}/offers/mine/clarifications").json()] == [q]
    r = sp.post(f"/projects/{pid}/offers/mine/clarifications/{q}/answer", json={"answer": "Brand X"})
    assert r.status_code == 200, r.text
    # Putting the offer forward again still needs an approved account.
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 403


def test_the_winner_under_re_review_still_sees_its_offer_and_reviews(db):
    owner = _account(db, "owner", "o-rereview-w@example.com")
    sp = _account(db, "service_provider", "s-rereview-w@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    oid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    owner.post(f"/owner/projects/{pid}/offers/{oid}/approve")
    complete_transaction(owner, sp, pid)
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 5}).status_code == 200
    _standing(db, sp, VerificationStatus.pending_review)

    assert sp.get(f"/projects/{pid}/offers/mine").json()["status"] == "approved"  # the page shows the agreement on this
    assert sp.get(f"/service-provider/projects/{pid}/review").status_code == 200
    assert sp.get(f"/service-provider/projects/{pid}/review/received").status_code == 200
    # A suspended or rejected account still loses sight of it.
    _standing(db, sp, VerificationStatus.pending_review, suspended=True)
    assert sp.get(f"/projects/{pid}/offers/mine").status_code == 403
    _standing(db, sp, VerificationStatus.rejected)
    assert sp.get(f"/projects/{pid}/offers/mine").status_code == 403


class _Session(dict):
    def __init__(self, sid, url="https://stripe.test/c", status="open"):
        super().__init__(id=sid, status=status)
        self.id, self.url = sid, url


def test_two_checkouts_cant_both_subscribe_and_a_stray_event_leaves_access_alone(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", SECRET)
    monkeypatch.setattr(get_settings(), "stripe_price_id_monthly", "price_m")
    amal, sami, x_id, _ = _organization(db, "service_provider", "X Contracting", "amal@x.example", "sami@x.example")
    cp = db.get(ServiceProviderProfile, x_id)
    cp.payment_override_active = False
    db.commit()
    sessions, expired = iter(["cs_A", "cs_B", "cs_C"]), []
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kw: _Session(next(sessions)))
    monkeypatch.setattr(stripe.checkout.Session, "expire", lambda sid: expired.append(sid))

    # Two colleagues open checkout: the first one's session is expired before the second starts.
    assert amal.post("/billing/checkout-session").status_code == 200
    assert sami.post("/billing/checkout-session").status_code == 200
    assert expired == ["cs_A"]

    # The second completes; the first can no longer be completed, but if Stripe still sent one
    # for another subscription, the live one held isn't swapped out.
    subs = {"sub_B": _sub("active", sub_id="sub_B"), "sub_A": _sub("active", sub_id="sub_A")}
    monkeypatch.setattr(stripe.Subscription, "retrieve", lambda sid: subs[sid])
    t0, meta = int(time.time()), {"service_provider_id": x_id}
    _post(_event("checkout.session.completed", {"object": "checkout.session", "id": "cs_B", "subscription": "sub_B", "customer": "cus_B", "metadata": meta}, t0, "e1"))
    _post(_event("checkout.session.completed", {"object": "checkout.session", "id": "cs_A", "subscription": "sub_A", "customer": "cus_A", "metadata": meta}, t0 + 1, "e2"))
    db.expire_all()
    cp = db.get(ServiceProviderProfile, x_id)
    assert (cp.stripe_subscription_id, cp.stripe_customer_id, cp.stripe_checkout_session_id) == ("sub_B", "cus_B", None)
    # The other subscription is cancelled in Stripe: its event leaves the held one's access alone.
    gone = _sub("canceled", sub_id="sub_A")
    gone["metadata"] = meta
    assert _post(_event("customer.subscription.deleted", gone, t0 + 10, "e3")).status_code == 200
    db.expire_all()
    cp = db.get(ServiceProviderProfile, x_id)
    assert cp.subscription_status.value == "active" and cp.is_verified_active


def test_a_checkout_that_already_completed_isnt_followed_by_another(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_price_id_monthly", "price_m")
    sp = _account(db, "service_provider", "s-checkout-done@example.com")
    db.get(ServiceProviderProfile, _me(sp)).payment_override_active = False
    db.commit()
    monkeypatch.setattr(stripe.checkout.Session, "create", lambda **kw: _Session("cs_1"))
    assert sp.post("/billing/checkout-session").status_code == 200

    def cant_expire(sid):
        raise stripe.error.InvalidRequestError("already complete", None)

    monkeypatch.setattr(stripe.checkout.Session, "expire", cant_expire)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", lambda sid: _Session(sid, status="complete"))
    r = sp.post("/billing/checkout-session")  # before its webhook arrives
    assert r.status_code == 409 and "just set up" in r.json()["detail"]


def test_billing_stays_reachable_whatever_the_accounts_standing(db, monkeypatch):
    sp = _account(db, "service_provider", "s-portal@example.com")
    profile = db.get(ServiceProviderProfile, _me(sp))
    profile.stripe_customer_id = "cus_1"
    db.commit()
    monkeypatch.setattr(stripe.billing_portal.Session, "create", lambda **kw: _Session("bps_1", url="https://stripe.test/portal"))
    for status, suspended in ((VerificationStatus.changes_requested, False), (VerificationStatus.rejected, False), (VerificationStatus.approved, True)):
        _standing(db, sp, status, suspended)
        r = sp.post("/billing/portal-session")
        assert r.status_code == 200 and r.json()["url"] == "https://stripe.test/portal", (status, suspended, r.text)


def _tab(email):
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    assert c.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    return c


def _seen(client, pid):
    return {"X-Offer-Documents": ",".join(sorted(d["token"] for d in client.get(f"/projects/{pid}/offers/documents").json()))}


def _upload(client, pid, name):
    return client.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": (name, b"%PDF-1", "application/pdf")})


def test_documents_changed_elsewhere_are_never_submitted_unseen(db):
    owner = _account(db, "owner", "o-docs-seen@example.com")
    tab1 = _account(db, "service_provider", "s-docs-seen@example.com")
    pid = _tender(owner)
    tab1.post(f"/projects/{pid}/participate")
    _upload(tab1, pid, "reviewed.pdf")
    saved = tab1.put(f"/projects/{pid}/offers/draft", json={"amount": "1000", "message": "M", "accepted_declarations": [DECL],
                                                               "proposed_start_date": _d(20), "proposed_duration_days": 30}).json()
    seen = _seen(tab1, pid)  # what tab 1 shows
    _upload(_tab("s-docs-seen@example.com"), pid, "unseen.pdf")  # another tab replaces it

    r = tab1.post(f"/projects/{pid}/offers/draft/submit", headers={"If-Match": str(saved["draft_version"]), **seen})
    assert r.status_code == 409 and "documents were changed" in r.json()["detail"]
    # Reloaded, it goes with what is now shown.
    r = tab1.post(f"/projects/{pid}/offers/draft/submit", headers={"If-Match": str(saved["draft_version"]), **_seen(tab1, pid)})
    assert r.status_code == 200, r.text
    offer = db.query(Offer).filter(Offer.project_id == pid).one()
    db.refresh(offer)
    assert [d["file_name"] for d in offer.submitted_documents] == ["unseen.pdf"]

    # Revising works the same way.
    seen = _seen(tab1, pid)
    _upload(_tab("s-docs-seen@example.com"), pid, "later.pdf")
    body = {"amount": "900", "message": "M2", "accepted_declarations": [DECL], "proposed_start_date": _d(20), "proposed_duration_days": 30}
    r = tab1.post(f"/projects/{pid}/offers", json=body, headers={"If-Match": str(r.json()["revision"]), **seen})
    assert r.status_code == 409 and "documents were changed" in r.json()["detail"]


def test_whose_requirement_it_is_reaches_a_provider_only_with_an_award(db):
    owner = _account(db, "owner", "o-who@example.com")
    winner = _account(db, "service_provider", "s-who-win@example.com")
    other = _account(db, "service_provider", "s-who-other@example.com")
    pid = _tender(owner, title="First job")
    _submitted(winner, pid)
    _submitted(other, pid)
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"title": "First job (gate)"}, headers={"If-Match": str(v)}).status_code == 200

    for sp in (winner, other):
        assert sp.get(f"/projects/{pid}").json()["owner_id"] is None
        cards = sp.get("/service-provider/feed").json()["items"]
        assert cards and all(c["owner_id"] is None for c in cards)
        assert [a["created_by"] for a in sp.get(f"/projects/{pid}/amendments").json()] == [None]
    assert owner.get(f"/projects/{pid}/amendments").json()[0]["created_by"] is not None  # the owner side still sees its own

    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{winner.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    assert winner.get(f"/projects/{pid}").json()["owner_id"] == _me(owner)  # awarded: theirs to know
    assert other.get(f"/projects/{pid}").json()["owner_id"] is None

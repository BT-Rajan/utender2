"""Batch D: faults found by the independent review of Batches A-C. Each test
reproduces one of them through the real API, now corrected."""
from datetime import datetime, timedelta

from app.models.clarification import Clarification
from app.models.enums import SubscriptionStatus, VerificationStatus
from app.models.offer import Offer
from app.models.project import Project
from app.models.review import Review
from app.models.service_provider import ServiceProviderProfile
from app.routers.agreements import kuwait_today
from tests.stage7_helpers import put_in_force
from tests.test_batch_a_contract_logic import _awarded, _v
from tests.test_batch_b_tender_fairness import _validity_tender
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender


def test_the_founder_of_an_organisation_cannot_be_removed(db):
    rep, member, rep_id, member_id = _organization(db, "service_provider", "Shield W.L.L.", "founder@shield.example", "eng2@shield.example")
    # The representative role is handed over; the new representative then
    # tries to remove the founder, whose account holds the organisation's profile.
    assert rep.post(f"/account/organization/representative/{member_id}").status_code == 200
    r = member.delete(f"/account/organization/members/{rep_id}")
    assert r.status_code == 409, r.text
    # The founder is still listed as a member, not left half-removed.
    assert rep_id in {m["user_id"] for m in member.get("/account/organization/members").json()}


def test_a_winner_whose_documents_are_back_under_review_keeps_the_job_page(db):
    owner, sp, pid, base = _awarded(db, "rereview")
    profile = db.get(ServiceProviderProfile, sp.get("/auth/me").json()["id"])
    for status in (VerificationStatus.changes_requested, VerificationStatus.pending_review):
        profile.verification_status = status
        db.commit()
        # The requirement page carries the agreement panel, so it must open.
        assert sp.get(f"/projects/{pid}").status_code == 200, status
        assert sp.get(base).status_code == 200, status
    # Only a refused account loses sight of it.
    profile.verification_status = VerificationStatus.rejected
    db.commit()
    assert sp.get(f"/projects/{pid}").status_code == 404


def test_changing_the_signed_papers_needs_the_provider_to_confirm_again(db):
    owner, sp, pid, base = _awarded(db, "papers")
    pdf = {"file": ("signed.pdf", b"%PDF signed", "application/pdf")}
    assert owner.patch(base, json={"effective_date": kuwait_today().isoformat()}, headers=_v(owner, pid)).status_code == 200
    assert sp.post(f"{base}/confirm", headers=_v(sp, pid)).status_code == 200
    # The owner swaps the paperwork after the provider confirmed.
    doc = owner.post(f"{base}/documents", data={"kind": "work_order"}, files=pdf).json()
    assert doc["provider_confirmed_at"] is None
    assert owner.post(f"{base}/activate", headers=_v(owner, pid)).status_code == 400
    # Confirm again, then remove the paper: that is a change too.
    assert sp.post(f"{base}/confirm", headers=_v(sp, pid)).status_code == 200
    doc_id = doc["documents"][0]["id"]
    assert owner.delete(f"{base}/documents/{doc_id}").json()["provider_confirmed_at"] is None


def test_a_lapsed_subscription_does_not_stop_confirming_after_the_close(db):
    owner = _account(db, "owner", "o-lapsedsub@example.com")
    sp = _account(db, "service_provider", "s-lapsedsub@example.com")
    pid = _validity_tender(owner, days=10)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    offer_id = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    project = db.get(Project, pid)
    project.closed_at = datetime.utcnow() - timedelta(days=11)
    profile = db.get(ServiceProviderProfile, sp.get("/auth/me").json()["id"])
    profile.payment_override_active, profile.subscription_status = False, SubscriptionStatus.past_due
    db.commit()
    # The owner can't award the lapsed offer until the provider confirms it ...
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve").status_code == 409
    # ... and the provider can, without a live subscription, so nobody is stuck.
    assert sp.post(f"/projects/{pid}/offers/confirm").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve").status_code == 200


def test_the_closed_offer_status_has_a_translation():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "translations.ts").read_text(encoding="utf-8")
    assert text.count("offer_closed") >= 3  # the type, English and Arabic


def test_the_provider_can_terminate_after_the_owner_leaves_finished_work_unanswered(db):
    owner, sp, pid, base = _awarded(db, "overdue")
    put_in_force(owner, sp, pid)
    assert sp.post(f"{base}/start-work", json={}, headers=_v(sp, pid)).status_code == 200
    assert sp.post(f"{base}/completion/submit", json={}, headers=_v(sp, pid)).status_code == 200
    r = sp.post(f"{base}/terminate", json={"reason": "No answer."}, headers=_v(sp, pid))
    assert r.status_code == 409  # still within the owner's review period
    agreement = db.query(__import__("app.models.agreement", fromlist=["Agreement"]).Agreement).filter_by(project_id=pid).one()
    assert sp.get(base).json()["completion_review_overdue"] is False
    agreement.completion_submitted_at = datetime.utcnow() - timedelta(days=31)
    db.commit()
    assert sp.get(base).json()["completion_review_overdue"] is True  # the panel offers termination again
    r = sp.post(f"{base}/terminate", json={"reason": "No answer."}, headers=_v(sp, pid))
    assert r.status_code == 200 and r.json()["status"] == "terminated", r.text


def test_reviews_are_stamped_in_utc_by_the_application(db):
    column = Review.__table__.c.created_at
    assert column.default is not None  # not left to the database server's local clock
    assert abs((column.default.arg(None) - datetime.utcnow()).total_seconds()) < 5


def test_answers_to_the_providers_own_private_questions_are_counted(db):
    owner = _account(db, "owner", "o-priv@example.com")
    sp = _account(db, "service_provider", "s-priv@example.com")
    asker = _account(db, "service_provider", "a-priv@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    _submitted(asker, pid)
    q = asker.post(f"/projects/{pid}/clarifications", json={"question": "Is the parapet included?"}).json()
    # A question from before answers were shared with everyone: private to its asker.
    row = db.get(Clarification, q["id"])
    row.shared_with_all = False
    db.commit()
    assert owner.post(f"/projects/{pid}/clarifications/{q['id']}/answer", json={"answer": "Yes."}).status_code == 200
    row = db.get(Clarification, q["id"])
    row.shared_with_all = False
    db.commit()
    assert asker.get(f"/projects/{pid}/offers/mine").json()["answers_since"] == 1
    assert sp.get(f"/projects/{pid}/offers/mine").json()["answers_since"] == 0  # not theirs to see


def test_an_offer_whose_start_date_has_passed_cannot_be_confirmed_or_awarded(db):
    owner = _account(db, "owner", "o-start@example.com")
    sp = _account(db, "service_provider", "s-start@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    offer_id = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    offer = db.get(Offer, offer_id)
    offer.proposed_start_date = (datetime.utcnow() - timedelta(days=2)).date()
    db.commit()
    r = owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve")
    assert r.status_code == 409 and "start date" in r.json()["detail"]
    r = sp.post(f"/projects/{pid}/offers/confirm")
    assert r.status_code == 400 and "start date" in r.json()["detail"]

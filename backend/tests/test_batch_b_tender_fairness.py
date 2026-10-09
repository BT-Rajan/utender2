"""Batch B: the tender treats every provider alike and its outcome is plain.
Each test is one of the business-logic faults found in the end-to-end
review, now refused or corrected:

- every answer reaches every provider; an answer published after an offer is
  flagged on it; a material change reopens questions;
- an offer holds its price for the validity period only, and is awarded only
  as its provider stands by it (current version, within validity);
- a requirement ending without an award closes its offers; closing with no
  live offer expires it; evaluation starting is announced; counts leave
  withdrawn offers out;
- no earlier deadline once published, no early close while providers are
  still preparing, two withdrawals are final, no zero-priced item."""
from datetime import datetime, timedelta

from app.models.enums import NotificationType, OfferStatus, ProjectStatus
from app.models.notification import Notification
from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _when
from tests.test_stage5_13_revise import DECL, _submitted, _tender


def _types(db, user_id):
    return [n.type for n in db.query(Notification).filter(Notification.user_id == user_id)]


def _me(c):
    return c.get("/auth/me").json()["id"]


def _validity_tender(owner, days=30):
    pid = owner.post("/projects", data={"title": "Roof works", "address": "Salmiya", "description": "Waterproofing.", "bid_deadline": _when(10),
                                       "tender_type": "owner_visible"}).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"approach": "required", "documents": [{"name": "Method statement", "required": True}], "declarations": [DECL]})
    assert owner.put(f"/projects/{pid}/tender-rules", json={"commercial_conditions": {"offer_validity_days": days}}).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def test_every_answer_reaches_every_provider_and_flags_earlier_offers(db):
    owner = _account(db, "owner", "o-qa@example.com")
    asker = _account(db, "service_provider", "s-asker@example.com")
    other = _account(db, "service_provider", "s-other@example.com")
    pid = _tender(owner)
    _submitted(other, pid)
    # Asked "privately": the answer still goes to everyone, asker anonymous.
    q = asker.post(f"/projects/{pid}/clarifications", json={"question": "Is the parapet included?", "shared_with_all": False}).json()
    assert q["shared_with_all"] is True
    assert other.get(f"/projects/{pid}/clarifications").json() == []  # unanswered: the asker's own
    r = owner.post(f"/projects/{pid}/clarifications/{q['id']}/answer", json={"answer": "Yes, 40 m of parapet.", "shared_with_all": False})
    assert r.status_code == 200 and r.json()["shared_with_all"] is True
    seen = other.get(f"/projects/{pid}/clarifications").json()
    assert [c["answer"] for c in seen] == ["Yes, 40 m of parapet."] and seen[0]["service_provider_id"] is None
    assert NotificationType.clarification_shared in _types(db, _me(other))
    # The offer made before it is flagged, for its provider and the owner.
    assert other.get(f"/projects/{pid}/offers/mine").json()["answers_since"] == 1
    assert owner.get(f"/owner/projects/{pid}/offers").json()[0]["answers_since"] == 1


def test_a_material_change_reopens_questions(db):
    owner = _account(db, "owner", "o-reopen@example.com")
    sp = _account(db, "service_provider", "s-reopen@example.com")
    pid = owner.post("/projects", data={"title": "Fit-out", "address": "Kaifan", "description": "Office.", "bid_deadline": _when(10),
                                       "tender_type": "owner_visible"}).json()["id"]
    cutoff = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0).isoformat() + "Z"
    assert owner.put(f"/projects/{pid}/tender-rules", json={"questions_allowed": True, "questions_deadline": cutoff}).status_code == 200
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    # The question cut-off passes.
    project = db.get(Project, pid)
    project.questions_deadline = datetime.utcnow() - timedelta(hours=1)
    db.commit()
    assert sp.post(f"/projects/{pid}/clarifications", json={"question": "Ceiling height?"}).status_code == 400
    # A change to what providers price reopens them.
    r = owner.patch(f"/projects/{pid}", json={"description": "Office and pantry."})
    assert r.status_code == 200, r.text
    db.expire_all()
    project = db.get(Project, pid)
    assert project.material_revision == 1 and project.questions_deadline > datetime.utcnow() + timedelta(days=1, hours=23)
    assert sp.post(f"/projects/{pid}/clarifications", json={"question": "Ceiling height?"}).status_code == 201


def test_offers_hold_their_price_for_the_validity_period_only(db):
    owner = _account(db, "owner", "o-valid@example.com")
    sp = _account(db, "service_provider", "s-valid@example.com")
    pid = _validity_tender(owner, days=30)
    _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    offer_id = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    mine = sp.get(f"/projects/{pid}/offers/mine").json()
    assert mine["valid_until"] is not None and mine["validity_lapsed"] is False
    # Within validity the provider is held to it.
    assert sp.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    # Forty days later the price no longer binds.
    project = db.get(Project, pid)
    project.closed_at = datetime.utcnow() - timedelta(days=40)
    db.commit()
    seen = owner.get(f"/owner/projects/{pid}/offers").json()[0]
    assert seen["validity_lapsed"] is True
    r = owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve", json={"acknowledge_earlier_version": True})
    assert r.status_code == 409 and "validity" in r.json()["detail"]
    # The owner asks; the provider is told, confirms, and it can be awarded.
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/request-confirmation").status_code == 200
    assert NotificationType.offer_confirmation_requested in _types(db, _me(sp))
    confirmed = sp.post(f"/projects/{pid}/offers/confirm")
    assert confirmed.status_code == 200 and confirmed.json()["validity_lapsed"] is False
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve").status_code == 200


def test_a_lapsed_offer_can_be_withdrawn_after_the_close(db):
    owner = _account(db, "owner", "o-lapse@example.com")
    sp = _account(db, "service_provider", "s-lapse@example.com")
    pid = _validity_tender(owner, days=10)
    _submitted(sp, pid)
    owner.post(f"/owner/projects/{pid}/close")
    project = db.get(Project, pid)
    project.closed_at = datetime.utcnow() - timedelta(days=11)
    db.commit()
    r = sp.post(f"/projects/{pid}/offers/withdraw")
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"


def test_an_offer_on_an_earlier_version_is_awarded_only_once_its_provider_confirms(db):
    owner = _account(db, "owner", "o-stale@example.com")
    sp = _account(db, "service_provider", "s-stale@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    assert owner.patch(f"/projects/{pid}", json={"description": "Substation and cabling."}).status_code == 200
    owner.post(f"/owner/projects/{pid}/close")
    offer_id = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    # The owner's word alone is no longer enough.
    r = owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve", json={"acknowledge_earlier_version": True})
    assert r.status_code == 409 and "Ask the provider" in r.json()["detail"]
    assert sp.post(f"/projects/{pid}/offers/confirm").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve").status_code == 200


def test_ending_without_award_closes_offers_and_counts_leave_withdrawn_out(db):
    owner = _account(db, "owner", "o-end@example.com")
    a = _account(db, "service_provider", "s-end-a@example.com")
    b = _account(db, "service_provider", "s-end-b@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert owner.get(f"/projects/{pid}").json()["offer_count"] == 1
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    # Evaluation starting is announced to the bidders.
    assert owner.post(f"/owner/projects/{pid}/start-evaluation").status_code == 200
    assert NotificationType.evaluation_started in _types(db, _me(a))
    assert owner.post(f"/owner/projects/{pid}/no-award", json={}).status_code == 200
    db.expire_all()
    statuses = {o.service_provider_id: o.status for o in db.query(Offer).filter(Offer.project_id == pid)}
    assert statuses == {_me(a): OfferStatus.closed, _me(b): OfferStatus.withdrawn}
    assert a.get(f"/projects/{pid}/offers/mine").json()["status"] == "closed"


def test_closing_with_no_live_offer_expires_it(db):
    owner = _account(db, "owner", "o-none@example.com")
    sp = _account(db, "service_provider", "s-none@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    sp.post(f"/projects/{pid}/offers/withdraw")
    r = owner.post(f"/owner/projects/{pid}/close")
    assert r.status_code == 200 and r.json()["status"] == "expired"


def test_no_earlier_deadline_and_no_early_close_while_providers_prepare(db):
    owner = _account(db, "owner", "o-early@example.com")
    preparing = _account(db, "service_provider", "s-prep@example.com")
    bidder = _account(db, "service_provider", "s-bid@example.com")
    pid = _tender(owner)
    r = owner.patch(f"/projects/{pid}", json={"bid_deadline": _when(5)})
    assert r.status_code == 400 and "earlier" in r.json()["detail"]
    _submitted(bidder, pid)
    assert preparing.post(f"/projects/{pid}/participate").status_code in (200, 201)
    r = owner.post(f"/owner/projects/{pid}/close")
    assert r.status_code == 409 and "still preparing" in r.json()["detail"]
    assert db.get(Project, pid).status == ProjectStatus.open


def test_two_withdrawals_are_final(db):
    owner = _account(db, "owner", "o-wd@example.com")
    sp = _account(db, "service_provider", "s-wd@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    assert sp.post(f"/projects/{pid}/offers/withdraw").json()["withdrawals_left"] == 1
    body = {"amount": "950", "message": "Method", "assumptions": "A", "accepted_declarations": [DECL], "proposed_duration_days": 30}
    assert sp.post(f"/projects/{pid}/offers", json=body).status_code == 200
    assert sp.post(f"/projects/{pid}/offers/withdraw").json()["withdrawals_left"] == 0
    r = sp.post(f"/projects/{pid}/offers", json=body)
    assert r.status_code == 400 and "withdrawn twice" in r.json()["detail"]


def test_items_are_priced_above_zero(db):
    owner = _account(db, "owner", "o-zero@example.com")
    sp = _account(db, "service_provider", "s-zero@example.com")
    pid = owner.post("/projects", data={"title": "Paint", "address": "Hawally", "description": "Repaint.", "bid_deadline": _when(10),
                                       "tender_type": "owner_visible"}).json()["id"]
    items = owner.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [{"description": "Walls", "quantity": "100", "unit": "m2"}, {"description": "Primer"}]})
    assert items.status_code == 200, items.text
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    ids = [i["id"] for i in owner.get(f"/projects/{pid}").json()["items"]]
    sp.post(f"/projects/{pid}/participate")
    r = sp.post(f"/projects/{pid}/offers", json={"item_prices": [{"item_id": ids[0], "rate": "2.5"}, {"item_id": ids[1], "rate": "0"}], "proposed_duration_days": 10})
    assert r.status_code == 400 and "above zero" in r.json()["detail"]
    r = sp.post(f"/projects/{pid}/offers", json={"item_prices": [{"item_id": ids[0], "rate": "2.5"}, {"item_id": ids[1], "rate": "0.001"}], "proposed_duration_days": 10})
    assert r.status_code == 200, r.text

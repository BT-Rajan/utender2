"""Stage 6.10: clarification during evaluation. The owner's side asks one
provider to clarify their submitted offer, on the existing clarifications
record; only that offer's side sees and answers it; the answer sits beside
the offer and never changes it; only while offers are being evaluated."""
from app.models.audit_log import AuditLog
from app.models.clarification import Clarification
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.offer import Offer
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _submitted, _tender

Q = "Does your price include the 11 kV cable terminations?"


def _closed(db, owner, *providers, title="HV works"):
    pid = _tender(owner, title)
    for sp in providers:
        _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    return pid


def _offer_id(db, pid, sp):
    me = sp.get("/auth/me").json()["id"]
    return db.query(Offer).filter(Offer.project_id == pid, Offer.service_provider_id == me).one().id


def _ask(owner, pid, offer_id, question=Q):
    return owner.post(f"/owner/projects/{pid}/offers/{offer_id}/clarifications", json={"question": question})


def test_ask_answer_private_and_the_offer_never_changes(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _closed(db, owner, a, b)
    a_offer = _offer_id(db, pid, a)
    before = db.get(Offer, a_offer)
    stored = (before.amount, before.message, before.assumptions, before.proposed_start_date, before.proposed_duration_days, before.submitted_documents, before.revision, before.updated_at)

    r = _ask(owner, pid, a_offer)
    assert r.status_code == 201, r.text
    c = r.json()
    assert (c["offer_id"], c["offer_revision"], c["question"], c["answer"], c["asked_by_name"]) == (a_offer, 1, Q, None, "N")
    # A retry is the same question.
    assert _ask(owner, pid, a_offer).json()["id"] == c["id"]
    assert db.query(Clarification).filter(Clarification.offer_id == a_offer).count() == 1
    # A's side is told, and sees it on their own offer; B sees nothing of it, anywhere.
    a_id, b_id = a.get("/auth/me").json()["id"], b.get("/auth/me").json()["id"]
    assert db.query(Notification).filter(Notification.user_id == a_id, Notification.type == NotificationType.offer_clarification_requested).count() == 1
    assert [x["question"] for x in a.get(f"/projects/{pid}/offers/mine/clarifications").json()] == [Q]
    assert b.get(f"/projects/{pid}/offers/mine/clarifications").json() == []
    assert b.get(f"/owner/projects/{pid}/offers/{a_offer}/clarifications").status_code == 403
    for client in (a, b, owner):  # never in the requirement's public Q&A
        assert Q not in client.get(f"/projects/{pid}/clarifications").text
    assert db.query(Notification).filter(Notification.user_id == b_id, Notification.type == NotificationType.offer_clarification_requested).count() == 0

    # B can't answer it; nor can the owner through the requirement Q&A.
    assert b.post(f"/projects/{pid}/offers/mine/clarifications/{c['id']}/answer", json={"answer": "x"}).status_code == 404
    assert owner.post(f"/projects/{pid}/clarifications/{c['id']}/answer", json={"answer": "x"}).status_code == 404
    # A answers -- once.
    r = a.post(f"/projects/{pid}/offers/mine/clarifications/{c['id']}/answer", json={"answer": "  Yes, all 12 terminations are included.  "})
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "Yes, all 12 terminations are included."
    assert a.post(f"/projects/{pid}/offers/mine/clarifications/{c['id']}/answer", json={"answer": "Actually no."}).status_code == 400
    # The owner sees it beside the offer, and is told.
    seen = owner.get(f"/owner/projects/{pid}/offers/{a_offer}/clarifications").json()
    assert [(x["question"], x["answer"], x["answered_by_name"]) for x in seen] == [(Q, "Yes, all 12 terminations are included.", "N")]
    owner_id = owner.get("/auth/me").json()["id"]
    assert db.query(Notification).filter(Notification.user_id == owner_id, Notification.type == NotificationType.offer_clarification_answered).count() == 1
    # History: who asked, who answered, when, which offer.
    actions = [x.action for x in db.query(AuditLog).filter(AuditLog.target_id == a_offer).order_by(AuditLog.created_at)]
    assert actions.count("offer_clarification.ask") == 1 and actions.count("offer_clarification.answer") == 1
    # The offer is exactly as submitted.
    db.expire_all()
    after = db.get(Offer, a_offer)
    assert (after.amount, after.message, after.assumptions, after.proposed_start_date, after.proposed_duration_days, after.submitted_documents, after.revision, after.updated_at) == stored
    assert owner.get(f"/owner/projects/{pid}/offers/{a_offer}").json()["offer"]["amount"] == f"{stored[0]:.3f}"


def test_ids_are_checked_together_and_no_one_else_asks(db):
    owner = _account(db, "owner", "owner@example.com")
    stranger = _account(db, "owner", "stranger@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _closed(db, owner, a)
    other = _closed(db, owner, b, title="Elsewhere")
    b_offer_elsewhere = _offer_id(db, other, b)
    # B's offer on another requirement, under this requirement's path: not found.
    assert _ask(owner, pid, b_offer_elsewhere).status_code == 404
    assert _ask(stranger, pid, _offer_id(db, pid, a)).status_code == 404
    assert _ask(a, pid, _offer_id(db, pid, a)).status_code == 403
    assert db.query(Clarification).count() == 0


def test_only_while_offers_are_being_evaluated(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    # Open: providers can still formally revise, so there's nothing to clarify yet.
    open_pid = _tender(owner, "Open")
    _submitted(a, open_pid)
    assert _ask(owner, open_pid, _offer_id(db, open_pid, a)).status_code == 400
    # Closed (past the deadline): asked, and answered after the deadline.
    pid = _closed(db, owner, a, b)
    a_offer, b_offer = _offer_id(db, pid, a), _offer_id(db, pid, b)
    c = _ask(owner, pid, a_offer).json()
    pending = _ask(owner, pid, b_offer).json()
    assert a.post(f"/projects/{pid}/offers/mine/clarifications/{c['id']}/answer", json={"answer": "Yes."}).status_code == 200
    # Offers can't be withdrawn or revised once closed, and the requirement can't be amended: the context stays fixed.
    assert b.post(f"/projects/{pid}/offers/withdraw").status_code == 400
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"description": "Changed after the clarification."}, headers={"If-Match": str(v)}).status_code in (400, 409)
    assert owner.get(f"/projects/{pid}").json()["material_revision"] == 0
    # An admin-suspended offer can't be clarified.
    db.get(Offer, b_offer).is_suspended = True
    db.commit()
    assert b.post(f"/projects/{pid}/offers/mine/clarifications/{pending['id']}/answer", json={"answer": "Late."}).status_code == 400
    db.get(Offer, b_offer).is_suspended = False
    db.commit()
    # After the outcome (awarded): neither asked nor answered; the history stays.
    assert owner.post(f"/owner/projects/{pid}/offers/{a_offer}/approve").status_code == 200
    assert _ask(owner, pid, a_offer, "One more?").status_code == 400
    assert b.post(f"/projects/{pid}/offers/mine/clarifications/{pending['id']}/answer", json={"answer": "Late."}).status_code == 400
    assert [x["answer"] for x in owner.get(f"/owner/projects/{pid}/offers/{a_offer}/clarifications").json()] == ["Yes."]
    assert [x["answer"] for x in b.get(f"/projects/{pid}/offers/mine/clarifications").json()] == [None]
    # A suspended requirement: nothing asked.
    p2 = _closed(db, owner, a, title="Suspended")
    assert _admin(db).post(f"/admin/projects/{p2}/suspend", json={"suspended": True}).status_code == 200
    r = _ask(owner, p2, _offer_id(db, p2, a))
    assert r.status_code == 400 and "suspended" in r.json()["detail"]

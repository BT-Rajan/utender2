"""Stage 7.3: the agreement governing an awarded requirement -- one per award,
created with it, reading its parties, value, offer and scope version from the
award record; the parties attach the signed papers; the owner side records
when it takes effect or that it was terminated; only the owner side, the
winner's side and admins ever see it; the award itself never changes."""
from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement, AgreementDocument
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import OfferStatus, ProjectStatus
from app.models.offer import Offer
from app.models.project import Project
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _submitted, _tender

PDF = ("signed.pdf", b"%PDF-1.4 signed", "application/pdf")


def _awarded(db, organization="Gulf Holdings W.L.L."):
    owner = _account(db, "owner", "owner@example.com", organization=organization)
    win, lose, gone = (_account(db, "service_provider", f"{n}@example.com") for n in ("badr", "amal", "dana"))
    pid = _tender(owner)
    for sp in (win, lose, gone):
        _submitted(sp, pid)
    assert gone.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    wid = win.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    return owner, win, lose, gone, pid, wid


def _v(client, pid):
    return {"If-Match": str(client.get(f"/projects/{pid}/agreement").json()["version"])}


def test_the_whole_way_from_award_to_an_agreement_in_force(db):
    owner, win, lose, gone, pid, wid = _awarded(db)
    award = db.query(AwardRecord).one()
    (agreement,) = db.query(Agreement).all()  # created with the award
    assert (agreement.award_id, agreement.project_id, agreement.status) == (award.id, pid, "preparing")

    a = owner.get(f"/projects/{pid}/agreement").json()
    assert (a["id"], a["award_id"], a["offer_id"], a["amount"], a["currency"], a["side"]) == (agreement.id, award.id, wid, "1000.000", "KWD", "owner")
    assert (a["owner_name"], a["provider_name"], a["status"], a["documents"]) == ("Gulf Holdings W.L.L.", "badr", "preparing", [])
    assert a["awarded_at"].endswith("Z") and a["offer_revision"] == award.offer_revision

    # The papers: the winner attaches the signed agreement, the owner a purchase order.
    r = win.post(f"/projects/{pid}/agreement/documents", data={"kind": "signed_agreement"}, files={"file": PDF})
    assert r.status_code == 200, r.text
    r = owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "purchase_order"}, files={"file": ("po.pdf", b"%PDF po", "application/pdf")})
    assert {(d["kind"], d["party"]) for d in r.json()["documents"]} == {("signed_agreement", "provider"), ("purchase_order", "owner")}

    # The owner side records the reference and effective date, then puts it in force.
    assert owner.post(f"/projects/{pid}/agreement/activate", headers=_v(owner, pid)).status_code == 400  # no date yet
    r = owner.patch(f"/projects/{pid}/agreement", json={"reference": " PO-2026-114 ", "effective_date": "2026-11-01"}, headers=_v(owner, pid))
    assert r.status_code == 200 and r.json()["reference"] == "PO-2026-114"
    r = owner.post(f"/projects/{pid}/agreement/activate", headers=_v(owner, pid))
    assert r.status_code == 200 and r.json()["status"] == "active" and r.json()["activated_at"].endswith("Z")

    # Both parties see the same agreement, papers and all.
    for client, side in ((owner, "owner"), (win, "provider"), (_admin(db), "admin")):
        a = client.get(f"/projects/{pid}/agreement").json()
        assert (a["status"], a["reference"], a["effective_date"], a["side"], len(a["documents"])) == ("active", "PO-2026-114", "2026-11-01", side, 2)
        assert client.get(f"/projects/{pid}/agreement/documents/{a['documents'][0]['id']}/file", follow_redirects=False).status_code == 303
    actions = {r.action for r in db.query(AuditLog).filter(AuditLog.target_id == agreement.id)}
    assert actions == {"agreement.document_add", "agreement.update", "agreement.activate"}

    # The award and the history it rests on are untouched.
    db.expire_all()
    assert (db.get(Project, pid).status, db.get(Offer, wid).status) == (ProjectStatus.awarded, OfferStatus.approved)
    assert (db.query(AwardRecord).one().amount, db.query(AwardRecord).one().offer_id) == (award.amount, wid)


def test_no_one_else_reaches_it_by_any_id(db):
    owner, win, lose, gone, pid, wid = _awarded(db)
    win.post(f"/projects/{pid}/agreement/documents", data={"kind": "signed_agreement"}, files={"file": PDF})
    doc = db.query(AgreementDocument).one()
    others = (lose, gone, _account(db, "service_provider", "outsider@example.com"), _account(db, "owner", "other@example.com", organization="Other Co"))
    for client in others:
        assert client.get(f"/projects/{pid}/agreement").status_code == 404
        assert client.get(f"/projects/{pid}/agreement/documents/{doc.id}/file", follow_redirects=False).status_code == 404
        assert client.post(f"/projects/{pid}/agreement/documents", data={"kind": "other"}, files={"file": PDF}).status_code == 404
        assert client.post(f"/projects/{pid}/agreement/activate").status_code == 404
        assert client.post(f"/projects/{pid}/agreement/terminate", json={"reason": "x"}).status_code == 404
        assert client.delete(f"/projects/{pid}/agreement/documents/{doc.id}").status_code == 404
    assert TestClient(app).get(f"/projects/{pid}/agreement").status_code == 401

    # A document id from this agreement, asked for under another requirement of the same owner.
    other_pid = _tender(owner)
    assert owner.get(f"/projects/{other_pid}/agreement/documents/{doc.id}/file", follow_redirects=False).status_code == 404
    # Only the owner side changes its details or status; the admin only reads.
    assert win.post(f"/projects/{pid}/agreement/activate").status_code == 403
    assert win.patch(f"/projects/{pid}/agreement", json={"reference": "mine"}).status_code == 403
    assert _admin(db).post(f"/projects/{pid}/agreement/terminate", json={"reason": "x"}).status_code == 403
    # A side removes only its own papers.
    assert owner.delete(f"/projects/{pid}/agreement/documents/{doc.id}").status_code == 403
    assert db.query(AgreementDocument).count() == 1


def test_organization_members_share_it_not_just_whoever_awarded(db):
    from tests.test_organization_sharing import _organization

    fahad, noura, *_ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    sp = _account(db, "service_provider", "badr@example.com")
    pid = _tender(fahad)
    _submitted(sp, pid)
    fahad.post(f"/owner/projects/{pid}/close")
    wid = sp.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert fahad.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    # A colleague who didn't award it records the agreement.
    r = noura.patch(f"/projects/{pid}/agreement", json={"effective_date": "2026-11-01"}, headers=_v(noura, pid))
    assert r.status_code == 200 and r.json()["side"] == "owner"
    assert fahad.get(f"/projects/{pid}/agreement").json()["effective_date"] == "2026-11-01"


def test_stale_tabs_double_clicks_and_endings(db):
    owner, win, lose, gone, pid, wid = _awarded(db)
    stale = _v(owner, pid)
    assert owner.patch(f"/projects/{pid}/agreement", json={"effective_date": "2026-11-01"}, headers=stale).status_code == 200
    assert owner.patch(f"/projects/{pid}/agreement", json={"effective_date": "2027-01-01"}, headers=stale).status_code == 409  # the other tab
    fresh = _v(owner, pid)
    assert owner.post(f"/projects/{pid}/agreement/activate", headers=fresh).status_code == 200
    assert owner.post(f"/projects/{pid}/agreement/activate", headers=fresh).status_code == 400  # the double-click
    assert owner.patch(f"/projects/{pid}/agreement", json={"effective_date": "2027-01-01"}, headers=_v(owner, pid)).status_code == 400  # in force
    assert owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "  "}, headers=_v(owner, pid)).status_code == 400
    r = owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Provider could not mobilise."}, headers=_v(owner, pid))
    assert r.status_code == 200 and (r.json()["status"], r.json()["termination_reason"]) == ("terminated", "Provider could not mobilise.")
    assert owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "again"}).status_code == 400
    assert win.post(f"/projects/{pid}/agreement/documents", data={"kind": "other"}, files={"file": PDF}).status_code == 400
    # Terminated, the award still stands exactly as it was made.
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded and db.query(AwardRecord).one().offer_id == wid
    assert db.query(Agreement).count() == 1
    assert win.get(f"/projects/{pid}/agreement").json()["status"] == "terminated"


def test_documents_bad_kind_bad_type_and_removal(db):
    owner, win, lose, gone, pid, wid = _awarded(db)
    assert owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "contract_template"}, files={"file": PDF}).status_code == 400
    assert owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "other"}, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "other"}, files={"file": ("x.pdf", b"", "application/pdf")}).status_code == 400
    doc_id = owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "work_order"}, files={"file": PDF}).json()["documents"][0]["id"]
    assert owner.delete(f"/projects/{pid}/agreement/documents/{doc_id}").json()["documents"] == []  # while preparing
    doc_id = owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "work_order"}, files={"file": PDF}).json()["documents"][0]["id"]
    owner.patch(f"/projects/{pid}/agreement", json={"effective_date": "2026-11-01"}, headers=_v(owner, pid))
    owner.post(f"/projects/{pid}/agreement/activate", headers=_v(owner, pid))
    assert owner.delete(f"/projects/{pid}/agreement/documents/{doc_id}").status_code == 400  # in force: on record


def test_no_award_no_agreement(db):
    owner = _account(db, "owner", "owner@example.com")
    sp = _account(db, "service_provider", "badr@example.com")
    pid = _tender(owner)
    _submitted(sp, pid)
    assert owner.get(f"/projects/{pid}/agreement").status_code == 404  # still open
    owner.post(f"/owner/projects/{pid}/close")
    assert owner.post(f"/owner/projects/{pid}/no-award", json={}).status_code == 200
    for client in (owner, sp):
        assert client.get(f"/projects/{pid}/agreement").status_code == 404
        assert client.post(f"/projects/{pid}/agreement/documents", data={"kind": "other"}, files={"file": PDF}).status_code == 404
    assert db.query(Agreement).count() == 0


def test_a_suspended_requirement_or_account_freezes_it(db):
    owner, win, lose, gone, pid, wid = _awarded(db)
    project = db.get(Project, pid)
    project.is_suspended = True
    db.commit()
    assert win.get(f"/projects/{pid}/agreement").status_code == 404
    assert owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "other"}, files={"file": PDF}).status_code == 400
    project.is_suspended = False
    db.commit()
    from app.models.service_provider import ServiceProviderProfile

    db.get(ServiceProviderProfile, win.get("/auth/me").json()["id"]).is_suspended = True
    db.commit()
    assert win.get(f"/projects/{pid}/agreement").status_code == 404

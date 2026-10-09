"""Stage 7.9: execution evidence. Photographs, site, delivery, completion and
inspection reports and test results are agreement documents of an evidence
kind, attached once the work has started -- to the transaction, to one
deliverable or to one progress update of that same agreement, never two,
never another's. Either party may add them; only the parties (and admins)
open them; uploading changes no status; requirement, offer and agreement
papers are untouched."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import AgreementDocument, ExecutionUpdate, Milestone
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.enums import ProjectStatus
from app.models.offer import OfferDocument
from app.models.project import Project
from app.routers import agreements as agreements_router
from app.services.storage import get_storage
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _submitted, _tender
from tests.stage7_helpers import put_in_force

PHOTO = ("level-3-progress.jpg", b"\xff\xd8\xff photo", "image/jpeg")
REPORT = ("inspection.pdf", b"%PDF inspection", "application/pdf")


def _a(client, pid):
    return client.get(f"/projects/{pid}/agreement").json()


def _v(client, pid):
    return {"If-Match": str(_a(client, pid)["version"])}


def _evidence(client, pid, kind, f=PHOTO, **links):
    return client.post(f"/projects/{pid}/agreement/documents", data={"kind": kind, **links}, files={"file": f})


def _awarded(db, title="HV works", owner=None, a=None, b=None):
    owner = owner or _account(db, "owner", "owner@example.com", organization="Gulf Holdings W.L.L.")
    a = a or _account(db, "service_provider", "amal@example.com")
    b = b or _account(db, "service_provider", "badr@example.com")
    pid = _tender(owner, title=title)
    _submitted(a, pid)
    _submitted(b, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    wid = a.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    return owner, a, b, pid, wid


def test_progress_and_inspection_evidence_seen_by_both_parties_only(db):
    owner, a, b, pid, wid = _awarded(db)
    mid = owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "Level 3 slab"}, headers=_v(owner, pid)).json()["milestones"][0]["id"]
    owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "signed_agreement"}, files={"file": ("signed.pdf", b"%PDF s", "application/pdf")})
    put_in_force(owner, a, pid)  # Batch A: work starts only under an agreement in force
    assert _evidence(a, pid, "progress_photo").status_code == 400  # before the work starts: no execution evidence
    a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid))
    update_id = a.post(f"/projects/{pid}/agreement/progress", json={"action": "update", "note": "Slab poured."}, headers=_v(a, pid)).json()["execution_history"][-1]["id"]

    assert _evidence(a, pid, "progress_photo", execution_update_id=update_id).status_code == 200  # on the progress update
    assert _evidence(a, pid, "delivery_record", ("delivery.pdf", b"%PDF d", "application/pdf"), milestone_id=mid).status_code == 200  # on the deliverable
    r = _evidence(owner, pid, "inspection_report", REPORT)  # the owner's own inspection, on the transaction
    assert r.status_code == 200
    docs = {d["file_name"]: d for d in r.json()["documents"]}
    assert (docs["level-3-progress.jpg"]["evidence"], docs["level-3-progress.jpg"]["execution_update_id"], docs["level-3-progress.jpg"]["party"]) == (True, update_id, "provider")
    assert (docs["delivery.pdf"]["evidence"], docs["delivery.pdf"]["milestone_id"]) == (True, mid)
    assert (docs["inspection.pdf"]["evidence"], docs["inspection.pdf"]["party"]) == (True, "owner")
    assert docs["signed.pdf"]["evidence"] is False  # the agreement's own paper, kept apart

    for client in (owner, a, _admin(db)):
        for d in _a(client, pid)["documents"]:
            assert client.get(f"/projects/{pid}/agreement/documents/{d['id']}/file", follow_redirects=False).status_code == 303
    others = (b, _account(db, "service_provider", "rival@example.com", organization="Rival Contracting"), _account(db, "owner", "other@example.com", organization="Other Co"), TestClient(app))
    for client in others:
        assert client.get(f"/projects/{pid}/agreement").status_code in (401, 404)  # no metadata either
        for d in docs.values():
            assert client.get(f"/projects/{pid}/agreement/documents/{d['id']}/file", follow_redirects=False).status_code in (401, 404)
        assert _evidence(client, pid, "site_report", REPORT).status_code in (401, 404)

    # Nothing moved: no status, no milestone, no history entry, no pre-award paper.
    seen = _a(owner, pid)
    assert (seen["execution_status"], seen["milestones"][0]["status"]) == ("in_progress", "pending")
    assert [h["kind"] for h in seen["execution_history"]] == ["started", "progress"]
    assert db.query(OfferDocument).filter(OfferDocument.offer_id == wid).count() == 1
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded and db.query(AwardRecord).one().offer_id == wid
    assert db.query(AuditLog).filter(AuditLog.action == "agreement.document_add").count() == 4


def test_evidence_never_lands_on_another_transaction_or_two_contexts(db):
    owner, a, b, pid, wid = _awarded(db)
    _, _, _, pid2, _ = _awarded(db, title="Second", owner=owner, a=a, b=b)
    m2 = owner.post(f"/projects/{pid2}/agreement/milestones", json={"title": "Other job"}, headers=_v(owner, pid2)).json()["milestones"][0]["id"]
    for p in (pid, pid2):
        put_in_force(owner, a, p)  # Batch A: work starts only under an agreement in force
        a.post(f"/projects/{p}/agreement/start-work", json={}, headers=_v(a, p))
    u2 = _a(a, pid2)["execution_history"][0]["id"]
    assert _evidence(a, pid, "progress_photo", execution_update_id=u2).status_code == 404  # the other job's update
    assert _evidence(a, pid, "delivery_record", milestone_id=m2).status_code == 404  # the other job's deliverable
    assert _evidence(a, pid, "progress_photo", execution_update_id="not-an-update").status_code == 404
    u1 = _a(a, pid)["execution_history"][0]["id"]
    assert _evidence(a, pid2, "progress_photo", execution_update_id=u2, milestone_id=m2).status_code == 400  # two contexts
    assert _evidence(a, pid, "progress_photo", execution_update_id=u1).status_code == 200
    doc = db.query(AgreementDocument).one()
    assert owner.get(f"/projects/{pid2}/agreement/documents/{doc.id}/file", follow_redirects=False).status_code == 404
    assert _a(owner, pid2)["documents"] == []
    assert db.get(Milestone, m2).status == "pending"


def test_evidence_through_hold_termination_and_failures(db, monkeypatch):
    owner, a, b, pid, wid = _awarded(db)
    put_in_force(owner, a, pid)  # Batch A: in force before the start (previously activated after the work had started)
    a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid))
    a.post(f"/projects/{pid}/agreement/progress", json={"action": "hold", "note": "Storm damage."}, headers=_v(a, pid))
    r = _evidence(a, pid, "site_report", REPORT)  # on hold: evidence of why is welcome
    assert r.status_code == 200 and _a(a, pid)["execution_status"] == "on_hold"  # and changes nothing
    keep = r.json()["documents"][0]["id"]

    class Broken:
        def save(self, *args):
            raise OSError("disk full")

    monkeypatch.setattr(agreements_router, "get_storage", lambda: Broken())
    with pytest.raises(OSError):
        _evidence(a, pid, "progress_photo")
    monkeypatch.undo()
    assert db.query(AgreementDocument).count() == 1  # the failed upload left nothing

    assert a.delete(f"/projects/{pid}/agreement/documents/{keep}").status_code == 400  # in force: evidence stays on record
    owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Stopped."}, headers=_v(owner, pid))
    assert _evidence(a, pid, "progress_photo").status_code == 400  # terminated: no more evidence
    assert a.get(f"/projects/{pid}/agreement/documents/{keep}/file", follow_redirects=False).status_code == 303  # history stays
    assert b.get(f"/projects/{pid}/agreement/documents/{keep}/file", follow_redirects=False).status_code == 404
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded  # nothing reopened or closed


def test_file_safety_is_the_existing_one(db):
    owner, a, b, pid, wid = _awarded(db)
    put_in_force(owner, a, pid)  # Batch A: work starts only under an agreement in force
    a.post(f"/projects/{pid}/agreement/start-work", json={}, headers=_v(a, pid))
    assert _evidence(a, pid, "progress_photo", ("payload.exe", b"MZ", "application/octet-stream")).status_code == 400
    assert _evidence(a, pid, "progress_photo", ("photo.jpg", b"", "image/jpeg")).status_code == 400
    assert _evidence(a, pid, "selfie").status_code == 400  # not a kind
    r = _evidence(a, pid, "site_report", ("../../etc/passwd.pdf", b"%PDF x", "application/pdf"))
    assert r.status_code == 200
    doc = db.query(AgreementDocument).one()
    assert ".." not in doc.file_path and doc.file_name == "etc/passwd.pdf"
    assert doc.file_path.startswith(f"{pid}/") and doc.id in doc.file_path  # private, keyed by an unguessable id
    assert get_storage().exists(agreements_router.AGREEMENT_BUCKET, doc.file_path)
    link = a.get(f"/projects/{pid}/agreement/documents/{doc.id}/file", follow_redirects=False).headers["location"]
    assert "sig=" in link and "exp=" in link  # a short-lived signed link, never a public one
    tampered = link.replace("sig=", "sig=0")
    assert TestClient(app).get(tampered.replace("http://localhost:8000", "")).status_code == 403


def test_no_award_no_evidence(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    assert _evidence(a, pid, "progress_photo").status_code == 404
    assert db.query(ExecutionUpdate).count() == 0 and db.query(AgreementDocument).count() == 0

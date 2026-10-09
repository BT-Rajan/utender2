"""Stage 7.4: contract documents. The papers of the post-award relationship
are the agreement's documents (7.3): kept apart from requirement and offer
documents, attached to exactly one agreement -- so one award, one
requirement, one owner side and one winning side -- opened only by those
parties (and admins), however ids are swapped; a failed upload leaves
nothing behind; the award never moves because a document did."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement, AgreementDocument
from app.models.award_record import AwardRecord
from app.models.enums import OfferStatus, ProjectStatus
from app.models.offer import Offer, OfferDocument
from app.models.project import Project
from app.routers import agreements as agreements_router
from app.services.storage import get_storage
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage5_13_revise import _submitted, _tender

BUCKET = agreements_router.AGREEMENT_BUCKET


def _award(owner, winner, others=(), title="HV works"):
    pid = _tender(owner, title=title)
    for sp in (winner, *others):
        _submitted(sp, pid)
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    wid = winner.get(f"/projects/{pid}/offers/mine").json()["id"]
    assert owner.post(f"/owner/projects/{pid}/offers/{wid}/approve").status_code == 200
    return pid, wid


def _attach(client, pid, kind, name="paper.pdf", body=b"%PDF paper"):
    return client.post(f"/projects/{pid}/agreement/documents", data={"kind": kind}, files={"file": (name, body, "application/pdf")})


def _opens(client, pid, doc_id):
    return client.get(f"/projects/{pid}/agreement/documents/{doc_id}/file", follow_redirects=False).status_code


@pytest.fixture
def awarded(db):
    owner = _account(db, "owner", "owner@example.com", organization="Gulf Holdings W.L.L.")
    a, b = _account(db, "service_provider", "amal@example.com"), _account(db, "service_provider", "badr@example.com")
    pid, wid = _award(owner, a, (b,))
    return owner, a, b, pid, wid


def test_owner_and_winner_exchange_papers_and_no_one_else_sees_them(db, awarded):
    owner, a, b, pid, wid = awarded
    award_before = {c: getattr(db.query(AwardRecord).one(), c) for c in ("id", "offer_id", "service_provider_id", "amount", "offer_revision")}

    signed = _attach(owner, pid, "signed_agreement", "signed.pdf").json()["documents"][0]
    cert = next(d for d in _attach(a, pid, "certificate", "insurance.pdf").json()["documents"] if d["kind"] == "certificate")
    for client in (owner, a, _admin(db)):
        docs = client.get(f"/projects/{pid}/agreement").json()["documents"]
        assert {(d["kind"], d["party"], d["file_name"]) for d in docs} == {("signed_agreement", "owner", "signed.pdf"), ("certificate", "provider", "insurance.pdf")}
        assert _opens(client, pid, signed["id"]) == _opens(client, pid, cert["id"]) == 303
    # Who uploaded it: the member's name for one's own side; the side for the other party.
    names = {d["kind"]: d["uploaded_by_name"] for d in owner.get(f"/projects/{pid}/agreement").json()["documents"]}
    assert names == {"signed_agreement": "N", "certificate": None}
    names = {d["kind"]: d["uploaded_by_name"] for d in a.get(f"/projects/{pid}/agreement").json()["documents"]}
    assert names == {"signed_agreement": None, "certificate": "N"}

    # Provider B, another owner, another provider organisation, nobody signed in.
    other_org = _account(db, "service_provider", "rival@example.com", organization="Rival Contracting")
    for client in (b, _account(db, "owner", "other@example.com", organization="Other Co"), other_org, TestClient(app)):
        assert client.get(f"/projects/{pid}/agreement").status_code in (401, 404)
        assert _opens(client, pid, signed["id"]) in (401, 404) and _opens(client, pid, cert["id"]) in (401, 404)
        assert client.delete(f"/projects/{pid}/agreement/documents/{cert['id']}").status_code in (401, 404)
    assert db.query(AgreementDocument).count() == 2

    # The pre-award documents are a different thing, and stay where they were.
    assert db.query(OfferDocument).filter(OfferDocument.offer_id == wid).count() == 1
    db.expire_all()
    assert {c: getattr(db.query(AwardRecord).one(), c) for c in award_before} == award_before
    assert (db.get(Project, pid).status, db.get(Offer, wid).status) == (ProjectStatus.awarded, OfferStatus.approved)


def test_a_document_never_crosses_into_another_transaction(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    p1, _ = _award(owner, a, title="Job one")
    p2, _ = _award(owner, a, title="Job two")  # same owner, same winner
    d1 = _attach(owner, p1, "work_order").json()["documents"][0]["id"]
    for client in (owner, a):
        assert _opens(client, p2, d1) == 404  # another transaction's id in the path
        assert client.get(f"/projects/{p2}/agreement").json()["documents"] == []
    assert owner.delete(f"/projects/{p2}/agreement/documents/{d1}").status_code == 404
    assert _opens(owner, p1, "not-a-document") == 404
    assert owner.get("/projects/not-a-requirement/agreement").status_code == 404
    doc = db.get(AgreementDocument, d1)
    assert doc.agreement_id == db.query(Agreement).filter(Agreement.project_id == p1).one().id


def test_same_name_same_moment_never_shares_a_stored_file(db, awarded):
    owner, a, b, pid, wid = awarded
    _attach(owner, pid, "other", "scan.pdf", b"%PDF owner")
    _attach(a, pid, "other", "scan.pdf", b"%PDF provider")
    paths = [d.file_path for d in db.query(AgreementDocument)]
    assert len(set(paths)) == 2
    mine = db.query(AgreementDocument).filter(AgreementDocument.party == "owner").one()
    assert owner.delete(f"/projects/{pid}/agreement/documents/{mine.id}").status_code == 200
    (theirs,) = db.query(AgreementDocument).all()
    assert get_storage().download(BUCKET, theirs.file_path) == b"%PDF provider"  # untouched
    assert not get_storage().exists(BUCKET, mine.file_path)
    assert db.query(Agreement).count() == 1  # removing a document never removes the agreement


def test_a_failed_upload_leaves_nothing_behind(db, awarded, monkeypatch):
    owner, a, b, pid, wid = awarded

    class Broken:
        def save(self, *args):
            raise OSError("disk full")

    monkeypatch.setattr(agreements_router, "get_storage", lambda: Broken())
    with pytest.raises(OSError):
        _attach(owner, pid, "signed_agreement")
    monkeypatch.undo()
    assert db.query(AgreementDocument).count() == 0

    # The record fails after the file was stored: the file goes too.
    saved = []
    real = get_storage()

    class Spy:
        def save(self, bucket, key, *rest):
            saved.append(key)
            real.save(bucket, key, *rest)

        def delete(self, bucket, keys):
            real.delete(bucket, keys)

    def failing_log(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(agreements_router, "get_storage", lambda: Spy())
    monkeypatch.setattr(agreements_router, "log_action", failing_log)
    with pytest.raises(RuntimeError):
        _attach(owner, pid, "signed_agreement")
    monkeypatch.undo()
    db.expire_all()
    assert db.query(AgreementDocument).count() == 0 and saved and not real.exists(BUCKET, saved[0])
    assert owner.get(f"/projects/{pid}/agreement").json()["documents"] == []


def test_removed_while_someone_opens_it_and_kept_once_in_force(db, awarded):
    owner, a, b, pid, wid = awarded
    doc = _attach(owner, pid, "final_quotation").json()["documents"][0]
    link = owner.get(f"/projects/{pid}/agreement/documents/{doc['id']}/file", follow_redirects=False).headers["location"]
    assert owner.delete(f"/projects/{pid}/agreement/documents/{doc['id']}").status_code == 200
    assert _opens(a, pid, doc["id"]) == 404  # the page the provider still had open
    assert TestClient(app).get(link.replace("http://localhost:8000", "")).status_code == 404  # an already-issued link finds nothing
    assert owner.delete(f"/projects/{pid}/agreement/documents/{doc['id']}").status_code == 404  # the second tab

    kept = _attach(a, pid, "signed_agreement").json()["documents"][0]["id"]
    v = owner.get(f"/projects/{pid}/agreement").json()["version"]
    owner.patch(f"/projects/{pid}/agreement", json={"effective_date": "2026-11-01"}, headers={"If-Match": str(v)})
    # Batch A: the provider confirms the terms before the owner can put it in force.
    assert a.post(f"/projects/{pid}/agreement/confirm", headers={"If-Match": str(v + 1)}).status_code == 200
    assert owner.post(f"/projects/{pid}/agreement/activate", headers={"If-Match": str(v + 2)}).status_code == 200
    assert a.delete(f"/projects/{pid}/agreement/documents/{kept}").status_code == 400  # in force: on record
    assert _attach(owner, pid, "purchase_order").status_code == 200  # still attachable while in force


def test_terminated_documents_stay_with_the_parties_only(db, awarded):
    owner, a, b, pid, wid = awarded
    doc = _attach(a, pid, "signed_agreement").json()["documents"][0]["id"]
    v = owner.get(f"/projects/{pid}/agreement").json()["version"]
    assert owner.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Mutual agreement."}, headers={"If-Match": str(v)}).status_code == 200
    assert _opens(owner, pid, doc) == _opens(a, pid, doc) == 303
    assert _opens(b, pid, doc) == 404
    assert _attach(owner, pid, "other").status_code == 400
    assert a.delete(f"/projects/{pid}/agreement/documents/{doc}").status_code == 400
    db.expire_all()
    assert db.get(Project, pid).status == ProjectStatus.awarded  # a document never reopens or moves the award


def test_leaving_the_organization_ends_access(db):
    from tests.test_organization_sharing import _organization

    fahad, noura, fahad_id, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    a = _account(db, "service_provider", "amal@example.com")
    pid, _ = _award(fahad, a)
    doc = _attach(noura, pid, "work_order").json()["documents"][0]["id"]
    assert _opens(fahad, pid, doc) == 303  # a colleague's upload is the side's
    assert fahad.delete(f"/account/organization/members/{noura_id}").status_code == 200
    assert _opens(noura, pid, doc) == 404 and noura.get(f"/projects/{pid}/agreement").status_code == 404
    assert _opens(fahad, pid, doc) == 303  # the organisation keeps it


def test_no_award_no_post_award_documents(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    for client in (owner, a):
        assert _attach(client, pid, "signed_agreement").status_code == 404
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/no-award", json={})
    assert _attach(owner, pid, "signed_agreement").status_code == 404
    assert db.query(AgreementDocument).count() == 0

"""Stage 7.16: the whole post-award journey, end to end, as one real
transaction: annual MEP maintenance of a commercial tower in Sharq, owned by
an organisation of two members, won by a two-member facilities company over
a cheaper individual bidder. Owner: create -> publish -> receive -> review ->
award -> agreement -> execution -> accept -> complete. Provider: discover ->
check eligibility -> offer -> win -> start -> progress -> deliver -> correct
-> accepted -> complete. At each boundary: the right requirement, offer,
organisations, documents, money, history -- and nobody else."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.agreement import Agreement, AgreementDocument, ExecutionUpdate, Milestone, Variation
from app.models.award_record import AwardRecord
from app.models.enums import OfferStatus, ProjectStatus
from app.models.offer import Offer, OfferDocument
from app.models.project import Project
from app.routers.agreements import kuwait_today
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account, _admin
from tests.test_stage6_17_end_to_end import DECL, _local, _offer, _tender

PDF = ("doc.pdf", b"%PDF doc", "application/pdf")


def _a(c, pid):
    return c.get(f"/projects/{pid}/agreement").json()


def _v(c, pid):
    return {"If-Match": str(_a(c, pid)["version"])}


def _mv(c, pid, mid):
    return {"If-Match": str(next(m for m in _a(c, pid)["milestones"] if m["id"] == mid)["version"])}


def test_a_maintenance_contract_from_requirement_to_closed_record(db):
    # --- Owner: create and publish. Provider: discover, check, offer. ---
    owner, colleague, *_ = _organization(db, "owner", "Al-Sabah Real Estate W.L.L.", "fahad@alsabah.example", "noura@alsabah.example")
    manara, technician, *_ = _organization(db, "service_provider", "Al Manara Facilities", "ops@manara.example", "tech@manara.example")
    rival = _account(db, "service_provider", "badr@example.com")
    pid = _tender(owner, title="Annual MEP maintenance — Sharq tower")
    assert pid in [p["id"] for p in technician.get("/service-provider/feed").json()["items"]]
    assert technician.get(f"/projects/{pid}/eligibility").json()["eligible"] is True
    win_id = _offer(technician, pid, "18000", "Planned-preventive programme")
    lose_id = _offer(rival, pid, "15500", "Reactive call-outs only", b"%PDF rival method")

    # --- Owner: review, evaluate privately, award. ---
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    detail = colleague.get(f"/owner/projects/{pid}/offers/{lose_id}").json()
    assert owner.get(_local(detail["offer"]["documents"][0]["url"])).content == b"%PDF rival method"
    owner.post(f"/owner/projects/{pid}/notes", json={"body": "Cheaper but no PPM programme.", "offer_id": lose_id})
    assert owner.post(f"/owner/projects/{pid}/offers/{win_id}/approve").status_code == 200

    db.expire_all()
    award = db.query(AwardRecord).one()
    agreement = db.query(Agreement).one()
    winner = db.get(Offer, win_id)
    assert (award.project_id, award.offer_id, award.amount) == (pid, win_id, 18000)
    assert (agreement.project_id, agreement.award_id, agreement.status) == (pid, award.id, "preparing")
    assert (db.get(Project, pid).status, winner.status, db.get(Offer, lose_id).status) == (ProjectStatus.awarded, OfferStatus.approved, OfferStatus.rejected)

    # --- Handover: both sides see the same transaction; the loser sees only the outcome. ---
    for c in (owner, colleague, manara, technician):
        seen = _a(c, pid)
        assert (seen["award_id"], seen["offer_id"], seen["owner_name"], seen["provider_name"], seen["original_amount"]) == (
            award.id, win_id, "Al-Sabah Real Estate W.L.L.", "Al Manara Facilities", "18000.000")
    loser_award = rival.get(f"/projects/{pid}/award").json()
    assert all(loser_award[k] is None for k in ("id", "offer_id", "amount", "owner_name"))

    # --- Agreement: deliverables, signed paper, in force. ---
    ppm = colleague.post(f"/projects/{pid}/agreement/milestones", json={"title": "Q1 PPM visit report", "due_date": (date.today() + timedelta(days=90)).isoformat()}, headers=_v(colleague, pid)).json()["milestones"][0]["id"]
    chiller = owner.post(f"/projects/{pid}/agreement/milestones", json={"title": "Chiller overhaul"}, headers=_v(owner, pid)).json()["milestones"][1]["id"]
    owner.post(f"/projects/{pid}/agreement/documents", data={"kind": "signed_agreement"}, files={"file": PDF})
    manara.post(f"/projects/{pid}/agreement/documents", data={"kind": "certificate"}, files={"file": ("insurance.pdf", b"%PDF ins", "application/pdf")})
    # Batch A: effective today in Kuwait (not tomorrow -- work can't start before it), and the provider confirms the terms first.
    owner.patch(f"/projects/{pid}/agreement", json={"reference": "PO-2026-311", "effective_date": kuwait_today().isoformat()}, headers=_v(owner, pid))
    assert technician.post(f"/projects/{pid}/agreement/confirm", headers=_v(technician, pid)).status_code == 200
    assert owner.post(f"/projects/{pid}/agreement/activate", headers=_v(owner, pid)).json()["status"] == "active"

    # --- Execution: start, progress with evidence, deliver / correct / accept, a change. ---
    assert technician.post(f"/projects/{pid}/agreement/start-work", json={"note": "Team mobilised."}, headers=_v(technician, pid)).status_code == 200
    upd = technician.post(f"/projects/{pid}/agreement/progress", json={"action": "update", "note": "AHU filters replaced, floors 1-12."}, headers=_v(technician, pid)).json()["execution_history"][-1]["id"]
    technician.post(f"/projects/{pid}/agreement/documents", data={"kind": "progress_photo", "execution_update_id": upd}, files={"file": ("ahu.jpg", b"\xff\xd8 photo", "image/jpeg")})
    technician.post(f"/projects/{pid}/agreement/documents", data={"kind": "site_report", "milestone_id": ppm}, files={"file": ("q1.pdf", b"%PDF q1", "application/pdf")})
    technician.post(f"/projects/{pid}/agreement/milestones/{ppm}/deliver", json={"note": "Q1 report attached."}, headers=_mv(technician, pid, ppm))
    colleague.post(f"/projects/{pid}/agreement/milestones/{ppm}/return", json={"note": "Add the chiller readings."}, headers=_mv(colleague, pid, ppm))
    technician.post(f"/projects/{pid}/agreement/milestones/{ppm}/deliver", json={"note": "Readings added."}, headers=_mv(technician, pid, ppm))
    owner.post(f"/projects/{pid}/agreement/milestones/{ppm}/accept", json={}, headers=_mv(owner, pid, ppm))
    vid = manara.post(f"/projects/{pid}/agreement/variations", json={"description": "Replace two corroded condenser coils.", "value_change": "2400", "add_deliverable": "Condenser coils replaced"}, headers=_v(manara, pid)).json()["variations"][0]["id"]
    v = _a(owner, pid)["variations"][0]
    assert manara.post(f"/projects/{pid}/agreement/variations/{vid}/agree", json={}, headers={"If-Match": str(v["version"])}).status_code == 403  # not its own
    owner.post(f"/projects/{pid}/agreement/variations/{vid}/agree", json={"note": "Approved."}, headers={"If-Match": str(v["version"])})
    coils = next(m["id"] for m in _a(owner, pid)["milestones"] if m["title"] == "Condenser coils replaced")
    for mid in (chiller, coils):
        technician.post(f"/projects/{pid}/agreement/milestones/{mid}/deliver", json={}, headers=_mv(technician, pid, mid))
        colleague.post(f"/projects/{pid}/agreement/milestones/{mid}/accept", json={}, headers=_mv(colleague, pid, mid))

    # --- Acceptance and completion. ---
    assert technician.post(f"/projects/{pid}/agreement/completion/submit", json={"note": "Year-one scope complete."}, headers=_v(technician, pid)).status_code == 200
    assert owner.post(f"/projects/{pid}/agreement/completion/accept", json={}, headers=_v(owner, pid)).status_code == 200
    assert owner.post(f"/projects/{pid}/agreement/completion/accept", json={}, headers={}).status_code == 409  # the retry

    # --- The closed record, as each side sees it. ---
    for c in (owner, technician):
        seen = _a(c, pid)
        assert (seen["status"], seen["execution_status"], seen["completion_status"]) == ("completed", "completed", "accepted")
        assert (seen["original_amount"], seen["agreed_changes_total"], seen["current_amount"], seen["currency"], seen["payment_tracking"]) == (
            "18000.000", "2400.000", "20400.000", "KWD", "not_managed")
        assert [m["status"] for m in seen["milestones"]] == ["accepted"] * 3
        kinds = [e["kind"] for e in seen["timeline"]]
        for earlier, later in (("awarded", "terms_confirmed"), ("terms_confirmed", "in_force"), ("in_force", "started"), ("returned", "change_proposed"), ("change_agreed", "completed")):
            assert kinds.index(earlier) < kinds.index(later), (earlier, later, kinds)
        assert kinds.count("completed") == 1 and kinds[-1] == "completed" and seen["timeline"][0]["amount"] == "18000.000"
        for d in seen["documents"]:
            assert c.get(f"/projects/{pid}/agreement/documents/{d['id']}/file", follow_redirects=False).status_code == 303
    papers = {d["file_name"]: d for d in _a(owner, pid)["documents"]}
    assert (papers["ahu.jpg"]["execution_update_id"], papers["q1.pdf"]["milestone_id"], papers["doc.pdf"]["evidence"]) == (upd, ppm, False)

    # --- Nothing reopens it; nobody else reaches it; history and award untouched. ---
    base = f"/projects/{pid}/agreement"
    for r in (technician.post(f"{base}/progress", json={"action": "update", "note": "late"}, headers={}),
              technician.post(f"{base}/milestones/{ppm}/deliver", json={}, headers={}),
              technician.post(f"{base}/documents", data={"kind": "progress_photo"}, files={"file": PDF}),
              owner.post(f"{base}/milestones/{ppm}/accept", json={}, headers={}),
              owner.post(f"{base}/variations", json={"description": "late"}, headers={}),
              technician.post(f"{base}/completion/submit", json={}, headers={})):
        assert r.status_code == 409, r.text
    outsider = _account(db, "owner", "other@example.com", organization="Other Holdings")
    for c in (rival, outsider, TestClient(app)):
        assert c.get(base).status_code in (401, 404)
        assert c.get(f"{base}/documents/{papers['doc.pdf']['id']}/file", follow_redirects=False).status_code in (401, 404)
    loser_doc = db.query(OfferDocument).filter(OfferDocument.offer_id == lose_id).one().id
    for c in (manara, technician):
        assert c.get(f"/owner/projects/{pid}/notes").status_code in (403, 404)
        assert c.get(f"/projects/{pid}/offers/documents/{loser_doc}/file", follow_redirects=False).status_code == 404
        assert "15500" not in c.get(base).text and "Cheaper but" not in c.get(base).text
    assert _admin(db).get(base).json()["status"] == "completed"
    db.expire_all()
    assert (db.query(AwardRecord).one().amount, db.get(Offer, win_id).amount) == (18000, 18000)
    assert db.query(Agreement).count() == 1 and db.query(Variation).count() == 1 and db.query(Milestone).count() == 3
    assert {d.agreement_id for d in db.query(AgreementDocument)} == {agreement.id}
    seqs = [u.sequence for u in db.query(ExecutionUpdate).order_by(ExecutionUpdate.sequence)]
    assert seqs == list(range(1, len(seqs) + 1))  # one unbroken history, no duplicates

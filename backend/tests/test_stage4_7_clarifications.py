"""Stage 4.7: provider questions on a published requirement -- asked from the
opportunity, answered by its owner side, kept with it, shared without saying
who asked, closed by the lifecycle and the question deadline, and tied to an
amendment when the answer changes the requirement itself."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.clarification import Clarification
from app.models.enums import VerificationStatus
from app.models.notification import Notification
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User

needs_mysql = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs real row locking (MySQL)")


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _verified(db, role, email, organization=None):
    c = TestClient(app)
    uid = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": email.split("@")[0].title(), "role": role}).json()["id"]
    c.put("/account/stakeholder", json={"type": "organization", "legal_name": organization, "authorized": True} if organization else {"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    p = db.get(model, uid)
    p.verification_status = VerificationStatus.approved
    if role == "service_provider":
        p.company_name = email.split("@")[0].title() + " Co"
        p.payment_override_active = True
    db.commit()
    return c


def _publish(owner, **extra):
    return owner.post("/projects", data={"title": "Villa rewiring", "address": "Kaifan", "description": "Rewire a villa: 40 points.", "bid_deadline": _when(10), "status": "open", **extra}).json()["id"]


def test_ask_answer_share_without_saying_who_asked(db):
    owner = _verified(db, "owner", "owner@example.com")
    noor, sami = _verified(db, "service_provider", "noor@example.com"), _verified(db, "service_provider", "sami@example.com")
    pid = _publish(owner)
    sami.post(f"/projects/{pid}/offers", json={"amount": "900"})
    # 1. A legitimate question, from the opportunity -- sent twice by a double click, kept once.
    q = noor.post(f"/projects/{pid}/clarifications", json={"question": "Are the 40 points including outdoor lighting?"})
    assert q.status_code == 201
    assert noor.post(f"/projects/{pid}/clarifications", json={"question": "Are the 40 points including outdoor lighting?"}).json()["id"] == q.json()["id"]
    assert db.query(Clarification).count() == 1
    # 2/12. The owner sees it (and is told).
    seen = owner.get(f"/projects/{pid}/clarifications").json()[0]
    assert seen["service_provider_company_name"] == "Noor Co"
    assert db.query(Notification).filter(Notification.type == "clarification_asked").count() == 1
    # 3/4. Answered, attached to the question, recorded with who and when.
    r = owner.post(f"/projects/{pid}/clarifications/{q.json()['id']}/answer", json={"answer": "No -- indoor points only."})
    assert r.status_code == 200 and r.json()["answer"] == "No -- indoor points only." and r.json()["answered_at"].endswith("Z")
    row = db.query(Clarification).one()
    owner_id = db.query(User).filter(User.email == "owner@example.com").one().id
    assert row.answered_by == owner_id and db.query(AuditLog).filter(AuditLog.action == "clarification.answer").count() == 1
    assert owner.get(f"/projects/{pid}/clarifications").json()[0]["answered_by_name"] == "Owner"
    # 5/6. Other providers see the shared Q&A -- not who asked; the asker sees it as theirs.
    other = sami.get(f"/projects/{pid}/clarifications").json()[0]
    assert other["answer"] == "No -- indoor points only." and other["service_provider_id"] is None and other["service_provider_company_name"] is None
    assert other["answered_by_name"] is None and other["mine"] is False and "Noor" not in str(other)
    assert noor.get(f"/projects/{pid}/clarifications").json()[0]["mine"] is True
    # 12. The asker is told; so is the bidder, as a published clarification.
    assert db.query(Notification).filter(Notification.type == "clarification_answered").count() == 1
    told = {n.user_id for n in db.query(Notification).filter(Notification.type == "clarification_shared")}
    assert told == {sami.get("/auth/me").json()["id"]}
    # Answered once: a second answer is refused.
    assert owner.post(f"/projects/{pid}/clarifications/{q.json()['id']}/answer", json={"answer": "Yes."}).status_code == 400


def test_a_private_question_the_owner_publishes_for_everyone(db):
    owner = _verified(db, "owner", "owner@example.com")
    noor, sami = _verified(db, "service_provider", "noor@example.com"), _verified(db, "service_provider", "sami@example.com")
    pid = _publish(owner)
    qid = noor.post(f"/projects/{pid}/clarifications", json={"question": "Is the DB board to be replaced?", "shared_with_all": False}).json()["id"]
    assert sami.get(f"/projects/{pid}/clarifications").json() == []  # private, unanswered
    owner.post(f"/projects/{pid}/clarifications/{qid}/answer", json={"answer": "Yes, a new 3-phase board.", "shared_with_all": True})
    shared = sami.get(f"/projects/{pid}/clarifications").json()
    assert [c["answer"] for c in shared] == ["Yes, a new 3-phase board."] and shared[0]["service_provider_company_name"] is None


def test_who_and_when_questions_are_accepted(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "noor@example.com")
    other_sp = _verified(db, "service_provider", "sami@example.com")
    # 8. Draft: no questions.
    draft = owner.post("/projects", data={"title": "Draft", "address": "x", "bid_deadline": _when(9)}).json()["id"]
    assert sp.post(f"/projects/{draft}/clarifications", json={"question": "?"}).status_code == 404
    # 7. Not eligible: no questions.
    restricted = owner.post("/projects", data={"title": "Substation", "address": "x", "description": "HV.", "bid_deadline": _when(9)}).json()["id"]
    owner.put(f"/projects/{restricted}/eligibility", json={"provider_type": "organization"})
    owner.post(f"/owner/projects/{restricted}/publish")
    assert sp.post(f"/projects/{restricted}/clarifications", json={"question": "Can individuals bid?"}).status_code == 404
    # 10. The question deadline, enforced -- and distinct from the offer deadline.
    pid = owner.post("/projects", data={"title": "Fence", "address": "x", "description": "Paint a fence.", "bid_deadline": _when(9)}).json()["id"]
    owner.put(f"/projects/{pid}/tender-rules", json={"questions_deadline": _when(3)})
    owner.post(f"/owner/projects/{pid}/publish")
    rules = sp.get(f"/projects/{pid}").json()["tender_rules"]
    assert rules["questions_close_at"] != sp.get(f"/projects/{pid}").json()["bid_deadline"] and rules["questions_open"] is True
    db.get(Project, pid).questions_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert sp.post(f"/projects/{pid}/clarifications", json={"question": "Late?"}).status_code == 400
    assert sp.post(f"/projects/{pid}/offers", json={"amount": "500"}).status_code == 200  # offers still open
    # 9. Ended: no new questions; the history stays for those entitled to it.
    open_pid = _publish(owner)
    qid = sp.post(f"/projects/{open_pid}/clarifications", json={"question": "Parking?"}).json()["id"]
    owner.post(f"/projects/{open_pid}/clarifications/{qid}/answer", json={"answer": "Street only."})
    sp.post(f"/projects/{open_pid}/offers", json={"amount": "900"})
    owner.post(f"/owner/projects/{open_pid}/cancel", json={"reason": "not_needed"})
    assert sp.post(f"/projects/{open_pid}/clarifications", json={"question": "Still?"}).status_code == 400
    assert [c["answer"] for c in sp.get(f"/projects/{open_pid}/clarifications").json()] == ["Street only."]
    assert other_sp.get(f"/projects/{open_pid}/clarifications").status_code == 404  # never took part


def test_no_one_answers_or_asks_as_someone_else(db):
    owner = _verified(db, "owner", "owner@example.com")
    other_owner = _verified(db, "owner", "other@example.com")
    noor, sami = _verified(db, "service_provider", "noor@example.com"), _verified(db, "service_provider", "sami@example.com")
    pid = _publish(owner)
    qid = noor.post(f"/projects/{pid}/clarifications", json={"question": "Parking?", "service_provider_id": "someone-else", "answer": "Yes"}).json()["id"]
    row = db.get(Clarification, qid)
    assert row.service_provider_id == noor.get("/auth/me").json()["id"] and row.answer is None  # 13. the server decides who and what
    assert sami.post(f"/projects/{pid}/clarifications/{qid}/answer", json={"answer": "Yes"}).status_code == 403
    assert other_owner.post(f"/projects/{pid}/clarifications/{qid}/answer", json={"answer": "Yes"}).status_code == 404
    assert db.get(Clarification, qid).answer is None


def test_an_answer_that_changes_the_requirement_goes_through_an_amendment(db):
    owner = _verified(db, "owner", "owner@example.com")
    noor, sami = _verified(db, "service_provider", "noor@example.com"), _verified(db, "service_provider", "sami@example.com")
    pid = _publish(owner)
    sami.post(f"/projects/{pid}/offers", json={"amount": "900"})
    qid = noor.post(f"/projects/{pid}/clarifications", json={"question": "Is outdoor lighting included?"}).json()["id"]
    owner.post(f"/projects/{pid}/clarifications/{qid}/answer", json={"answer": "Yes -- we'll add 6 outdoor points to the scope."})
    # 11. The answer alone changes nothing in the requirement.
    assert sami.get(f"/projects/{pid}").json()["material_revision"] == 0
    # The owner changes it through the amendment, tied to the question.
    v = owner.get(f"/projects/{pid}").json()["version"]
    r = owner.patch(f"/projects/{pid}", json={"description": "Rewire a villa: 40 points, plus 6 outdoor points.", "clarification_id": qid}, headers={"If-Match": str(v)})
    assert r.status_code == 200 and r.json()["material_revision"] == 1
    amendment = sami.get(f"/projects/{pid}/amendments").json()[-1]
    assert amendment["material"] and amendment["reason"].startswith("Following a question")
    assert sami.get(f"/projects/{pid}/clarifications").json()[0]["amendment_number"] == amendment["amendment_number"]
    assert sami.get(f"/projects/{pid}/offers/mine").json()["based_on_material_revision"] == 0  # the offer stays with what it priced
    # Only an answered question on this requirement can be named.
    other_q = noor.post(f"/projects/{pid}/clarifications", json={"question": "And the garage?"}).json()["id"]
    v = owner.get(f"/projects/{pid}").json()["version"]
    assert owner.patch(f"/projects/{pid}", json={"title": "Villa rewiring (rev)", "clarification_id": other_q}, headers={"If-Match": str(v)}).status_code == 400


@needs_mysql
def test_two_answers_at_once_keep_one(db):
    """14. Two people on the owner's side answering the same question at once."""
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "noor@example.com")
    pid = _publish(owner)
    qid = sp.post(f"/projects/{pid}/clarifications", json={"question": "Parking?"}).json()["id"]
    second = TestClient(app)
    second.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda a: a[0].post(f"/projects/{pid}/clarifications/{qid}/answer", json={"answer": a[1]}), [(owner, "Street only."), (second, "Basement.")]))
    assert sorted(r.status_code for r in results) == [200, 400]
    db.expire_all()
    winner = next(r.json()["answer"] for r in results if r.status_code == 200)
    assert db.get(Clarification, qid).answer == winner


def _fetch(client, url):
    return client.get("/" + url.split("://", 1)[-1].split("/", 1)[-1])


def test_files_on_questions_and_answers(db):
    owner = _verified(db, "owner", "owner@example.com")
    noor, sami = _verified(db, "service_provider", "noor@example.com"), _verified(db, "service_provider", "sami@example.com")
    outsider = _verified(db, "owner", "other@example.com")
    pid = _publish(owner)
    qid = noor.post(f"/projects/{pid}/clarifications", json={"question": "Which board is meant -- see my markup?"}).json()["id"]
    # The asker attaches a marked-up drawing to the question.
    r = noor.post(f"/projects/{pid}/clarifications/{qid}/attachments", files=[("files", ("markup.pdf", b"%PDF-markup", "application/pdf"))])
    assert r.status_code == 200 and [(a["part"], a["file_name"], a["size_bytes"]) for a in r.json()["attachments"]] == [("question", "markup.pdf", 11)]
    # Nobody else attaches to someone's question; types and counts are checked.
    assert sami.post(f"/projects/{pid}/clarifications/{qid}/attachments", files=[("files", ("x.pdf", b"%PDF", "application/pdf"))]).status_code == 404
    assert outsider.post(f"/projects/{pid}/clarifications/{qid}/attachments", files=[("files", ("x.pdf", b"%PDF", "application/pdf"))]).status_code == 404
    assert noor.post(f"/projects/{pid}/clarifications/{qid}/attachments", files=[("files", ("run.exe", b"MZ", "application/octet-stream"))]).status_code == 400
    assert noor.post(f"/projects/{pid}/clarifications/{qid}/attachments", files=[("files", ("bundle.zip", b"PK", "application/zip"))]).status_code == 400
    many = [("files", (f"p{i}.png", b"\x89PNG", "image/png")) for i in range(5)]
    assert noor.post(f"/projects/{pid}/clarifications/{qid}/attachments", files=many).status_code == 400  # 1 + 5 > 5
    # The owner sees the question's file; the answer gets its own.
    seen = owner.get(f"/projects/{pid}/clarifications").json()[0]
    assert _fetch(owner, seen["attachments"][0]["url"]).content == b"%PDF-markup"
    r = owner.post(f"/projects/{pid}/clarifications/{qid}/attachments", files=[("files", ("board-spec.pdf", b"%PDF-spec", "application/pdf"))])
    assert [a["part"] for a in r.json()["attachments"]] == ["question", "answer"]
    # Before the answer, the answer's file stays with the owner side.
    assert [a["part"] for a in noor.get(f"/projects/{pid}/clarifications").json()[0]["attachments"]] == ["question"]
    owner.post(f"/projects/{pid}/clarifications/{qid}/answer", json={"answer": "The main DB board; spec attached."})
    # Shared: every provider who may see it gets both files -- still without who asked.
    for client in (noor, sami):
        c = client.get(f"/projects/{pid}/clarifications").json()[0]
        assert [a["file_name"] for a in c["attachments"]] == ["markup.pdf", "board-spec.pdf"]
        assert _fetch(client, c["attachments"][1]["url"]).content == b"%PDF-spec"
    assert sami.get(f"/projects/{pid}/clarifications").json()[0]["service_provider_company_name"] is None
    # Answered: the question's files are as they were.
    assert noor.post(f"/projects/{pid}/clarifications/{qid}/attachments", files=[("files", ("late.pdf", b"%PDF", "application/pdf"))]).status_code == 400
    # A private question's files stay private.
    private = noor.post(f"/projects/{pid}/clarifications", json={"question": "Our pricing approach?", "shared_with_all": False}).json()["id"]
    # Batch B: a new question is always stored shared, whatever the request says.
    assert db.get(Clarification, private).shared_with_all is True
    # Batch B: only a question stored privately before the change stays private;
    # simulate that legacy row directly in the DB.
    db.get(Clarification, private).shared_with_all = False
    db.commit()
    noor.post(f"/projects/{pid}/clarifications/{private}/attachments", files=[("files", ("our-rates.xlsx", b"PK-rates", "application/vnd.ms-excel"))])
    owner.post(f"/projects/{pid}/clarifications/{private}/attachments", files=[("files", ("reply.pdf", b"%PDF-reply", "application/pdf"))])
    owner.post(f"/projects/{pid}/clarifications/{private}/answer", json={"answer": "Fine."})
    # Batch B: once answered it reaches the field, but its wording and the asker's
    # files stay private -- only the answer and the answer's files are shown.
    legacy = [c for c in sami.get(f"/projects/{pid}/clarifications").json() if c["id"] == private]
    assert len(legacy) == 1 and legacy[0]["question"] == "" and legacy[0]["answer"] == "Fine."
    assert [a["file_name"] for a in legacy[0]["attachments"]] == ["reply.pdf"]
    assert legacy[0]["service_provider_company_name"] is None and legacy[0]["service_provider_id"] is None
    # Closed Q&A: no more files.
    owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "not_needed"})
    assert owner.post(f"/projects/{pid}/clarifications/{qid}/attachments", files=[("files", ("x.pdf", b"%PDF", "application/pdf"))]).status_code == 400

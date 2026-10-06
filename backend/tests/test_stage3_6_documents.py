"""Stage 3.6: requirement documents. The owner attaches drawings, BOQs,
specifications, photos and site documents to a draft, labels what each is
and whether providers need it to price, removes or replaces them while it is
a draft, and finds them again later. Draft documents stay private; access
follows the requirement's existing visibility rules."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import ProjectDrawing
from app.models.service_provider import ServiceProviderProfile

DEADLINE = (datetime.utcnow() + timedelta(days=14)).isoformat()


def _verified(db, role: str, email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.payment_override_active = True
    db.commit()
    return c


def _upload(c, project_id, name, content=b"data", category="drawing", is_required=True):
    return c.post(
        f"/projects/{project_id}/drawings",
        files={"drawings": (name, content, "application/octet-stream")},
        data={"category": category, "is_required": str(is_required).lower()},
    )


def _docs(c, project_id):
    return {d["file_name"]: d for d in c.get(f"/projects/{project_id}").json()["drawings"]}


def test_owner_attaches_labels_removes_and_replaces_documents(db):
    owner = _verified(db, "owner", "owner@example.com")
    draft = owner.post("/projects", data={"title": "Majlis extension", "address": "Mishref", "bid_deadline": DEADLINE}).json()
    pid = draft["id"]

    assert _upload(owner, pid, "GA-plans.pdf", b"%PDF").status_code == 200
    assert _upload(owner, pid, "BOQ.xlsx", category="boq").status_code == 200
    assert _upload(owner, pid, "Specs.docx", category="specification").status_code == 200
    assert _upload(owner, pid, "site-front.jpg", category="photo", is_required=False).status_code == 200
    assert _upload(owner, pid, "macro.xlsm", category="boq").status_code == 400  # macro formats refused
    assert _upload(owner, pid, "x.pdf", category="invoice").status_code == 400  # unknown type

    # Leave and come back: everything is still there, labelled.
    again = TestClient(app)
    again.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
    docs = _docs(again, pid)
    assert {n: (d["category"], d["is_required"]) for n, d in docs.items()} == {
        "GA-plans.pdf": ("drawing", True),
        "BOQ.xlsx": ("boq", True),
        "Specs.docx": ("specification", True),
        "site-front.jpg": ("photo", False),
    }
    assert all(d["url"] for d in docs.values())  # owner can open each one

    # Re-label: the photo turns out to matter for pricing.
    r = again.patch(f"/projects/{pid}/drawings/{docs['site-front.jpg']['id']}", json={"is_required": True, "category": "site"})
    assert r.status_code == 200
    assert _docs(again, pid)["site-front.jpg"]["category"] == "site"

    # Replace: same name -> new revision of the same document.
    _upload(again, pid, "BOQ.xlsx", b"v2", category="boq")
    assert _docs(again, pid)["BOQ.xlsx"]["revision"] == 2

    # Remove: the document and its earlier revisions go.
    assert again.delete(f"/projects/{pid}/drawings/{_docs(again, pid)['BOQ.xlsx']['id']}").status_code == 200
    assert "BOQ.xlsx" not in _docs(again, pid)
    assert db.query(ProjectDrawing).filter(ProjectDrawing.file_name == "BOQ.xlsx").count() == 0


def test_draft_documents_stay_private_and_published_ones_follow_visibility(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sp@example.com")
    other = _verified(db, "owner", "other@example.com")

    draft = owner.post("/projects", data={"title": "Draft", "address": "A", "bid_deadline": DEADLINE}).json()
    _upload(owner, draft["id"], "plans.pdf", b"%PDF")
    doc_id = _docs(owner, draft["id"])["plans.pdf"]["id"]
    assert sp.get(f"/projects/{draft['id']}").status_code == 404
    assert sp.get(f"/projects/{draft['id']}/drawings-zip").status_code == 404
    assert sp.get(f"/projects/{draft['id']}/drawings/history").status_code == 404
    # Nobody else can add to, re-label or remove another owner's documents.
    assert _upload(other, draft["id"], "evil.pdf").status_code == 404
    assert other.patch(f"/projects/{draft['id']}/drawings/{doc_id}", json={"is_required": False}).status_code == 404
    assert other.delete(f"/projects/{draft['id']}/drawings/{doc_id}").status_code == 404

    # A document id from one requirement can't be used through another.
    mine = owner.post("/projects", data={"title": "Other draft", "address": "B", "bid_deadline": DEADLINE}).json()
    assert owner.delete(f"/projects/{mine['id']}/drawings/{doc_id}").status_code == 404

    # Once published, an eligible provider sees each document with its type and
    # a signed link; the documents can no longer be removed (only revised).
    published = owner.post("/projects", data={"title": "Live", "address": "C", "bid_deadline": DEADLINE, "status": "open"}).json()
    _upload(owner, published["id"], "BOQ.xlsx", category="boq")
    seen = _docs(sp, published["id"])["BOQ.xlsx"]
    assert seen["category"] == "boq" and seen["is_required"] is True and seen["url"]
    assert owner.delete(f"/projects/{published['id']}/drawings/{seen['id']}").status_code == 409

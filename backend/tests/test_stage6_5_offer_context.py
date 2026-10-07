"""Stage 6.5: requirement-to-offer context. Each offer keeps the requirement
version it answered (Stage 3.17's material revision); a material amendment
never makes an earlier offer look like it answered the new version, a
harmless correction never makes a valid offer look outdated, and a
replacement document belongs to the new version only -- atomically."""
import pytest

import app.routers.projects as projects_router
from app.models.offer import Offer
from app.models.project import Project, ProjectDrawing
from tests.test_stage4_9_participation import _account, _admin, _when
from tests.test_stage5_13_revise import REV2, _submitted

DECL = "I have visited the site."


def _tender(owner, title="HV works"):
    pid = owner.post("/projects", data={"title": title, "address": "Kaifan", "description": "Substation.", "bid_deadline": _when(10)},
                     files=[("drawings", ("sld.pdf", b"%PDF-v1", "application/pdf"))]).json()["id"]
    owner.put(f"/projects/{pid}/response-requirements", json={"approach": "required", "documents": [{"name": "Method statement", "required": True}], "declarations": [DECL]})
    assert owner.post(f"/owner/projects/{pid}/publish").status_code == 200
    return pid


def _amend(owner, pid, **fields):
    v = owner.get(f"/projects/{pid}").json()["version"]
    r = owner.patch(f"/projects/{pid}", json=fields, headers={"If-Match": str(v)})
    assert r.status_code == 200, r.text


def _context(owner, pid):
    return {o["service_provider_company_name"]: o["based_on_material_revision"] for o in owner.get(f"/owner/projects/{pid}/offers").json()}


def _detail(owner, pid, db, name):
    offer = next(o for o in owner.get(f"/owner/projects/{pid}/offers").json() if o["service_provider_company_name"] == name)
    return owner.get(f"/owner/projects/{pid}/offers/{offer['id']}").json()


def test_offers_keep_the_version_they_answered_across_a_material_amendment(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    _submitted(a, pid)  # against version 0
    before = db.query(Offer).one()
    stored = (before.amount, before.message, before.assumptions, before.item_prices, before.proposed_duration_days, before.submitted_documents)
    _amend(owner, pid, description="Substation plus a second bay.")
    _submitted(b, pid)  # against version 1
    assert _context(owner, pid) == {"amal": 0, "badr": 1}
    # The owner can tell them apart: A's is on the earlier version, B's on the current one.
    assert (_detail(owner, pid, db, "amal")["on_current_version"], _detail(owner, pid, db, "badr")["on_current_version"]) == (False, True)
    assert owner.get(f"/projects/{pid}/versions/0").json()["fields"]["description"] == "Substation."
    assert owner.get(f"/projects/{pid}/versions/1").json()["fields"]["description"] == "Substation plus a second bay."
    # A's offer is exactly as submitted -- the amendment changed nothing in it.
    db.expire_all()
    a_offer = db.get(Offer, before.id)
    assert (a_offer.amount, a_offer.message, a_offer.assumptions, a_offer.item_prices, a_offer.proposed_duration_days, a_offer.submitted_documents) == stored
    # A revises: now on version 1, with the version-0 offer kept in its history against version 0.
    assert a.post(f"/projects/{pid}/offers", json=REV2, headers={"If-Match": "1"}).status_code == 200
    assert _context(owner, pid) == {"amal": 1, "badr": 1}
    history = owner.get(f"/owner/projects/{pid}/offers/{before.id}/history").json()
    assert [(h["based_on_material_revision"], h["amount"], h["message"]) for h in history] == [(0, "1000.000", "Method v1")]


def test_harmless_corrections_leave_offers_current(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    _amend(owner, pid, title="HV works (corrected)")  # not material
    _amend(owner, pid, bid_deadline=_when(12))  # more time is not material
    assert owner.get(f"/projects/{pid}").json()["material_revision"] == 0
    assert _context(owner, pid) == {"amal": 0}
    assert _detail(owner, pid, db, "amal")["on_current_version"] is True


def test_a_replacement_document_belongs_to_the_new_version_only(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    r = owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("sld.pdf", b"%PDF-v2", "application/pdf"))])
    assert r.status_code == 200, r.text
    assert owner.get(f"/projects/{pid}").json()["material_revision"] == 1
    # A's offer answered version 0, whose single-line diagram is the first file -- not the replacement.
    assert _context(owner, pid) == {"amal": 0}
    v0 = owner.get(f"/projects/{pid}/versions/0").json()["documents"]
    v1 = owner.get(f"/projects/{pid}/versions/1").json()["documents"]
    assert [d["revision"] for d in v0] == [1] and [d["revision"] for d in v1] == [2]
    replacement = db.query(ProjectDrawing).filter(ProjectDrawing.project_id == pid, ProjectDrawing.revision == 2).one()
    assert replacement.material_revision == 1 and replacement.amendment_id is not None


def test_a_document_upload_and_its_amendment_land_together_or_not_at_all(db, monkeypatch):
    owner = _account(db, "owner", "owner@example.com")
    pid = _tender(owner)

    def failing(*args, **kwargs):
        raise RuntimeError("amendment could not be recorded")

    monkeypatch.setattr(projects_router, "_record_amendment", failing)
    with pytest.raises(RuntimeError):
        owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("sld.pdf", b"%PDF-v2", "application/pdf"))])
    db.expire_all()
    # Nothing of the upload stayed: the original is still the current file of version 0.
    rows = db.query(ProjectDrawing).filter(ProjectDrawing.project_id == pid).all()
    assert [(d.revision, d.is_current, d.material_revision) for d in rows] == [(1, True, 0)]
    assert db.get(Project, pid).material_revision == 0


def test_context_survives_the_requirement_lifecycle(db):
    owner = _account(db, "owner", "owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    admin = _admin(db)
    pid = _tender(owner)
    _submitted(a, pid)
    _amend(owner, pid, description="Substation plus a second bay.")
    _submitted(b, pid)
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True})
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": False})
    _amend(owner, pid, bid_deadline=_when(15))  # extended
    assert _context(owner, pid) == {"amal": 0, "badr": 1}
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    # Closed: the context stays readable, and stays what it was.
    assert _context(owner, pid) == {"amal": 0, "badr": 1}
    assert _detail(owner, pid, db, "amal")["on_current_version"] is False
    assert owner.post(f"/owner/projects/{pid}/close-externally", json={}).status_code == 200
    assert _context(owner, pid) == {"amal": 0, "badr": 1}

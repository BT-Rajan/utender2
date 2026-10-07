"""Stage 6.2: offer access & confidentiality. Only the requirement's owner side
reaches its offers, and only through the owner workflow; competitors,
unrelated owners and anonymous callers get nothing, whatever ids they put in;
a withdrawn offer's content stays the provider's; admin oversight is as
before; losing membership loses access at once."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.project import Project
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _admin
from tests.test_stage5_12_confidentiality import MARKERS, _ids, _parties, _submit, _sweep, _tender


def _secret(sp, pid):
    return _submit(sp, pid, "98765.432", "SECRET-METHOD-A7", "SECRET-ASSUME-A7", "SECRET-PERIOD-A7", ("secret-a7-method.pdf", b"%PDF-A7"))


def test_stress_only_the_owner_side_reaches_offers(db):
    owner, a, b, stranger_owner, unverified = _parties(db)
    pid = _tender(owner, sealed=False, title="Owner A's")
    other = _tender(stranger_owner, sealed=False, title="Owner B's")
    _secret(a, pid)
    _submit(b, pid, "11111", "Bravo method")
    _submit(b, other, "22222", "Bravo elsewhere")
    ids, a_offer, _ = _ids(db, pid, a, b)

    # Provider B, directly, with every id it could know or guess: nothing of A's offer.
    assert _sweep(b, ids) == []
    for path in (f"/owner/projects/{pid}/offers", f"/owner/projects/{pid}/offers/{a_offer.id}/history", "/admin/offers"):
        assert b.get(path).status_code in (403, 404), path
    assert b.patch(f"/admin/offers/{a_offer.id}", json={"amount": "1"}).status_code == 403
    # B never holds a link to A's document; B's own links are to B's file only.
    b_docs = b.get(f"/projects/{pid}/offers/documents").json()
    assert b_docs and not any("secret-a7" in d["url"] or "secret-a7" in d["file_name"] for d in b_docs)

    # Owner A on Requirement A: its offers, in full (owner-visible tender).
    listed = owner.get(f"/owner/projects/{pid}/offers").json()
    assert {o["amount"] for o in listed} == {"98765.432", "11111.000"}
    assert all(o["project_id"] == pid for o in listed)
    # Owner A swaps in Requirement B (someone else's), or B's offer under A's requirement: not found.
    other_offer = stranger_owner.get(f"/owner/projects/{other}/offers").json()[0]["id"]
    assert owner.get(f"/owner/projects/{other}/offers").status_code == 404
    assert owner.get(f"/owner/projects/{other}/offers/{other_offer}/history").status_code == 404
    assert owner.get(f"/owner/projects/{pid}/offers/{other_offer}/history").status_code == 404
    # Nor does an owner reach admin oversight.
    assert owner.get("/admin/offers").status_code == 403

    # No session: refused before anything is looked up.
    anonymous = TestClient(app)
    assert anonymous.get(f"/owner/projects/{pid}/offers").status_code == 401
    assert anonymous.get(f"/owner/projects/{pid}/offers/{a_offer.id}/history").status_code == 401
    assert anonymous.get(f"/projects/{pid}/offers/mine").status_code == 401
    # An unverified provider and an unrelated owner: nothing.
    assert _sweep(unverified, ids) == [] and _sweep(stranger_owner, ids) == []

    # Admin oversight, exactly as before: every offer, in full.
    admin = _admin(db)
    assert any(o["id"] == a_offer.id and o["amount"] == "98765.432" for o in admin.get("/admin/offers").json())


def test_a_withdrawn_offer_is_never_opened(db):
    owner, a, b, *_ = _parties(db)
    sealed, visible = _tender(owner, sealed=True, title="Sealed"), _tender(owner, sealed=False, title="Visible")
    for pid in (sealed, visible):
        _secret(a, pid)
        _submit(b, pid, "11111", "Bravo method")
        assert a.post(f"/projects/{pid}/offers/withdraw").status_code == 200
    # The sealed tender reaches its deadline: B's live offer opens; A's withdrawn one doesn't.
    db.get(Project, sealed).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    for pid in (sealed, visible):
        listed = owner.get(f"/owner/projects/{pid}/offers").json()
        withdrawn = [o for o in listed if o["status"] == "withdrawn"]
        assert len(withdrawn) == 1 and withdrawn[0]["service_provider_company_name"] == "alphasecret"
        assert not any(m in str(listed) for m in MARKERS if m != "alphasecret"), pid  # who withdrew is shown
        assert "11111" in str(listed)  # the live offer is there in full
        assert owner.get(f"/owner/projects/{pid}/offers/{withdrawn[0]['id']}/history").status_code == 404
    # The provider keeps their own withdrawn offer in full.
    assert a.get(f"/projects/{sealed}/offers/mine").json()["message"] == "SECRET-METHOD-A7"


def test_a_removed_member_loses_access_to_offers_at_once(db):
    fahad, noura, _, noura_id = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    _, a, *_ = _parties(db)
    pid = _tender(fahad, sealed=False)
    _secret(a, pid)
    offer_id = noura.get(f"/owner/projects/{pid}/offers").json()[0]["id"]
    assert noura.get(f"/owner/projects/{pid}/offers/{offer_id}/history").status_code == 200
    assert fahad.delete(f"/account/organization/members/{noura_id}").status_code == 200
    # The same session, the very next request.
    assert noura.get(f"/owner/projects/{pid}/offers").status_code == 404
    assert noura.get(f"/owner/projects/{pid}/offers/{offer_id}/history").status_code == 404
    assert len(fahad.get(f"/owner/projects/{pid}/offers").json()) == 1

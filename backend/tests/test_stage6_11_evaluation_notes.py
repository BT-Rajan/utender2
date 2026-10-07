"""Stage 6.11: evaluation notes. The owner side records private notes on its
requirement or on one of its offers; only that owner side reads them (its
organization's members, or the individual owner); only the author edits or
removes them; they're never attached to another requirement's offer and
outlive every change of state."""
from datetime import datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.evaluation_note import EvaluationNote
from app.models.offer import Offer
from app.models.project import Project
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender

NOTE = "Strong method statement; check the switchgear lead time with them."


def _offer_id(db, pid, sp):
    me = sp.get("/auth/me").json()["id"]
    return db.query(Offer).filter(Offer.project_id == pid, Offer.service_provider_id == me).one().id


def _note(owner, pid, body=NOTE, **extra):
    return owner.post(f"/owner/projects/{pid}/notes", json={"body": body, **extra})


def test_private_to_the_owner_side_and_kept_across_refresh(db):
    owner = _account(db, "owner", "owner@example.com")
    owner_b = _account(db, "owner", "other-owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid = _tender(owner)
    _submitted(a, pid)
    _submitted(b, pid)
    a_offer = _offer_id(db, pid, a)
    r = _note(owner, pid, offer_id=a_offer)
    assert r.status_code == 201, r.text
    note = r.json()
    assert (note["offer_id"], note["body"], note["mine"], note["author_name"], note["version"]) == (a_offer, NOTE, True, "N", 1)
    requirement_note = _note(owner, pid, "Budget ceiling 120k.").json()
    # After a refresh: the same notes, from the server.
    listed = owner.get(f"/owner/projects/{pid}/notes").json()
    # (in the order written; two notes within the same second are ordered by id)
    assert sorted((n["id"], n["offer_id"] or "") for n in listed) == sorted([(note["id"], a_offer), (requirement_note["id"], "")])
    assert [n["id"] for n in owner.get(f"/owner/projects/{pid}/notes", params={"offer_id": a_offer}).json()] == [note["id"]]
    # Nobody else: the provider it's about, a competitor, another owner, the public.
    from fastapi.testclient import TestClient
    from app.main import app
    for client, code in ((a, 403), (b, 403), (owner_b, 404), (TestClient(app), 401)):
        assert client.get(f"/owner/projects/{pid}/notes").status_code == code
        assert client.post(f"/owner/projects/{pid}/notes", json={"body": "x"}).status_code == code
        assert client.put(f"/owner/projects/{pid}/notes/{note['id']}", json={"body": "x"}).status_code == code
    # Nor through any read route a provider or another owner can reach.
    for client in (a, b, owner_b):
        for url in (f"/projects/{pid}", f"/projects/{pid}/offers/mine", f"/projects/{pid}/clarifications", "/service-provider/my-bids", "/owner/projects"):
            assert "lead time" not in client.get(url).text and "Budget ceiling" not in client.get(url).text, url


def test_notes_attach_only_to_this_requirements_offers(db):
    owner = _account(db, "owner", "owner@example.com")
    owner_b = _account(db, "owner", "other-owner@example.com")
    a, b = (_account(db, "service_provider", f"{n}@example.com") for n in ("amal", "badr"))
    pid, mine_too, sealed = _tender(owner, "Mine"), _tender(owner, "Also mine"), _tender(owner, "Sealed", sealed=True)
    theirs = _tender(owner_b, "Theirs")
    _submitted(a, pid)
    _submitted(b, mine_too)
    _submitted(a, theirs)
    _submitted(a, sealed)
    # Another requirement's offer -- the owner's own or someone else's -- under this requirement: refused, nothing saved.
    for offer_id in (_offer_id(db, mine_too, b), _offer_id(db, theirs, a), "no-such-offer"):
        assert _note(owner, pid, offer_id=offer_id).status_code == 404
    # Owner B can't write onto owner A's requirement, nor read A's notes through their own.
    a_note = _note(owner, pid, offer_id=_offer_id(db, pid, a)).json()
    assert owner_b.put(f"/owner/projects/{theirs}/notes/{a_note['id']}", json={"body": "x"}).status_code == 404
    assert owner_b.get(f"/owner/projects/{theirs}/notes").json() == []
    assert owner.put(f"/owner/projects/{mine_too}/notes/{a_note['id']}", json={"body": "x"}).status_code == 404  # a note is found under its own requirement only
    # Sealed and open: offers can't be told apart yet, so no notes on them -- a note on the requirement is fine.
    assert _note(owner, sealed, offer_id=_offer_id(db, sealed, a)).status_code == 404
    assert _note(owner, sealed, "Waiting for the deadline.").status_code == 201
    assert db.query(EvaluationNote).count() == 2


def test_organization_members_read_all_and_change_their_own(db):
    fahad, noura, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(fahad)
    _submitted(a, pid)
    offer_id = _offer_id(db, pid, a)
    mine = _note(fahad, pid, offer_id=offer_id).json()
    # A colleague in the same organization reads it (not theirs to change), and adds their own.
    seen = noura.get(f"/owner/projects/{pid}/notes").json()
    assert [(n["id"], n["mine"]) for n in seen] == [(mine["id"], False)]
    assert noura.put(f"/owner/projects/{pid}/notes/{mine['id']}", json={"body": "Rewritten"}).status_code == 403
    assert noura.delete(f"/owner/projects/{pid}/notes/{mine['id']}").status_code == 403
    assert _note(noura, pid, "Second opinion: agreed.", offer_id=offer_id).status_code == 201
    # The author edits: version moves on; an edit from a stale page is refused.
    r = fahad.put(f"/owner/projects/{pid}/notes/{mine['id']}", json={"body": "Updated after the site visit."}, headers={"If-Match": "1"})
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["updated_at"]
    assert fahad.put(f"/owner/projects/{pid}/notes/{mine['id']}", json={"body": "Stale tab."}, headers={"If-Match": "1"}).status_code == 409
    assert fahad.delete(f"/owner/projects/{pid}/notes/{mine['id']}", headers={"If-Match": "1"}).status_code == 409
    assert db.get(EvaluationNote, mine["id"]).body == "Updated after the site visit."
    # Audit: who added, edited.
    actions = {x.action for x in db.query(AuditLog).filter(AuditLog.target_id == mine["id"])}
    assert actions == {"evaluation_note.add", "evaluation_note.edit"}


def test_retries_are_one_note_and_notes_outlive_every_state(db):
    owner = _account(db, "owner", "owner@example.com")
    a = _account(db, "service_provider", "amal@example.com")
    pid = _tender(owner)
    _submitted(a, pid)
    offer_id = _offer_id(db, pid, a)
    first = _note(owner, pid, offer_id=offer_id, client_token="tab-1-submit-1").json()
    again = _note(owner, pid, offer_id=offer_id, client_token="tab-1-submit-1").json()
    assert first["id"] == again["id"] and db.query(EvaluationNote).count() == 1
    # Closed, awarded: still there, still the owner's only.
    assert owner.post(f"/owner/projects/{pid}/close").status_code == 200
    assert owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve").status_code == 200
    assert [n["body"] for n in owner.get(f"/owner/projects/{pid}/notes").json()] == [NOTE]
    assert NOTE not in a.get(f"/projects/{pid}/offers/mine").text and NOTE not in a.get(f"/projects/{pid}").text
    # Expired, cancelled, ended outside U-Tender: same.
    for end in ("expired", "cancel", "close-externally"):
        p = _tender(owner, end)
        _submitted(a, p)
        _note(owner, p, f"Note on {end}.")
        if end == "expired":
            db.get(Project, p).bid_deadline = datetime.utcnow() - timedelta(seconds=1)
            db.query(Offer).filter(Offer.project_id == p).delete()
            db.commit()
            owner.get("/owner/projects")  # the expiry sweep
        else:
            assert owner.post(f"/owner/projects/{p}/{end}", json={"reason": "not_needed"} if end == "cancel" else {}).status_code == 200
        assert [n["body"] for n in owner.get(f"/owner/projects/{p}/notes").json()] == [f"Note on {end}."], end
    # The author removes one: gone for everyone, recorded in the audit log.
    note_id = first["id"]
    assert owner.delete(f"/owner/projects/{pid}/notes/{note_id}").status_code == 204
    assert owner.get(f"/owner/projects/{pid}/notes").json() == []
    assert db.query(AuditLog).filter(AuditLog.target_id == note_id, AuditLog.action == "evaluation_note.delete").count() == 1

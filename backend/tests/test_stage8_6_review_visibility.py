"""Stage 8.6: who sees a completed review. The reviewer's side sees the review
it wrote; the reviewed side sees the review it received (rating, comment, date
-- no ids, no reviewer account); nobody else reads a review's content, whatever
id they send. Owners evaluating a provider see only its aggregate rating, as
before; a review never opens the transaction to anyone."""
from fastapi.testclient import TestClient

from app.main import app
from app.models.review import Review
from tests.stage7_helpers import complete_transaction
from tests.test_organization_sharing import _organization
from tests.test_stage4_9_participation import _account
from tests.test_stage5_13_revise import _submitted, _tender

OWNER_TEXT = "Excellent finish, on schedule."
PROVIDER_TEXT = "Clear scope and prompt payments."


def _received(client, side, pid):
    return client.get(f"/{side}/projects/{pid}/review/received")


def test_each_side_sees_what_it_wrote_and_what_it_received_and_no_one_else_does(db):
    owner, colleague, _, _ = _organization(db, "owner", "Gulf Holdings W.L.L.", "fahad@gulf.example", "noura@gulf.example")
    amal, sami, amal_id, sami_id = _organization(db, "service_provider", "Amal Contracting", "amal@amal.example", "sami@amal.example")
    loser = _account(db, "service_provider", "loser@example.com")  # Provider B, who bid and lost
    pid = _tender(owner, title="Tower maintenance")
    _submitted(sami, pid)
    _submitted(loser, pid)
    owner.post(f"/owner/projects/{pid}/close")
    owner.post(f"/owner/projects/{pid}/offers/{sami.get(f'/projects/{pid}/offers/mine').json()['id']}/approve")
    complete_transaction(owner, sami, pid)

    # Nothing is visible before a review is recorded, nor after a refused one.
    assert _received(sami, "service-provider", pid).json() is None
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 9, "comment": "never stored"}).status_code == 422
    assert _received(amal, "service-provider", pid).json() is None

    # Owner -> provider: the owner side sees what it wrote; the whole winning side sees what it received.
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 5, "comment": OWNER_TEXT}).status_code == 200
    assert owner.post("/owner/reviews", json={"project_id": pid, "rating": 1}).status_code == 409  # still one review
    assert colleague.get(f"/owner/projects/{pid}/review").json()["comment"] == OWNER_TEXT
    for client in (amal, sami):
        assert _received(client, "service-provider", pid).json() == {
            "rating": 5, "comment": OWNER_TEXT, "created_at": db.query(Review).one().created_at.isoformat() + "Z",
            "response": None, "response_at": None}
    # Provider -> owner, symmetrically.
    assert owner.get(f"/owner/projects/{pid}/review/received").json() is None
    assert sami.post("/service-provider/reviews", json={"project_id": pid, "rating": 4, "comment": PROVIDER_TEXT}).status_code == 200
    assert amal.get(f"/service-provider/projects/{pid}/review").json()["comment"] == PROVIDER_TEXT
    for client in (owner, colleague):
        got = _received(client, "owner", pid).json()
        assert set(got) == {"rating", "comment", "created_at", "response", "response_at"} and (got["rating"], got["comment"]) == (4, PROVIDER_TEXT)

    # Everyone else: the losing provider, an unrelated owner and provider, a role mismatch, no session.
    other_owner = _account(db, "owner", "other@example.com")
    rival = _account(db, "service_provider", "rival@example.com", organization="Rival Co")
    for client in (loser, rival):
        for path in ("review", "review/received"):
            assert client.get(f"/service-provider/projects/{pid}/{path}").status_code == 404
    for path in ("review", "review/received"):
        assert other_owner.get(f"/owner/projects/{pid}/{path}").status_code == 404
        assert sami.get(f"/owner/projects/{pid}/{path}").status_code == 403
        assert TestClient(app).get(f"/owner/projects/{pid}/{path}").status_code == 401
        assert TestClient(app).get(f"/service-provider/projects/{pid}/{path}").status_code == 401
    # Ids guessed from elsewhere lead nowhere: a review id or a party's id is not a project id.
    for guess in (db.query(Review).first().id, amal_id):
        assert other_owner.get(f"/owner/projects/{guess}/review/received").status_code == 404
        assert rival.get(f"/service-provider/projects/{guess}/review/received").status_code == 404
    # A removed member loses access with the organisation; the organisation keeps it.
    assert amal.delete(f"/account/organization/members/{sami_id}").status_code == 200
    assert _received(sami, "service-provider", pid).status_code in (403, 404)
    assert _received(amal, "service-provider", pid).json()["rating"] == 5

    # An owner evaluating Amal on a new requirement sees only the aggregate --
    # never a review's text, the earlier owner, or the earlier transaction.
    pid2 = _tender(other_owner, title="Warehouse roof")
    _submitted(amal, pid2)
    offers = other_owner.get(f"/owner/projects/{pid2}/offers")
    assert offers.status_code == 200
    offer = offers.json()[0]
    assert (float(offer["service_provider_avg_rating"]), offer["service_provider_review_count"]) == (5.0, 1)
    for text in (OWNER_TEXT, PROVIDER_TEXT, pid, "Tower maintenance", "Gulf Holdings"):
        assert text not in offers.text
    # Reading a review never opens the transaction: outsiders still can't reach it.
    for client in (loser, rival):
        assert client.get(f"/projects/{pid}/agreement").status_code in (403, 404)
    assert other_owner.get(f"/projects/{pid}/agreement").status_code in (403, 404)

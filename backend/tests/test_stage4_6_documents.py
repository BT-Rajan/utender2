"""Stage 4.6: the documents of a published requirement reach exactly the
providers entitled to them -- current ones clearly current, earlier ones kept
with the version they belonged to -- through short-lived signed links that
name the file, can't be redirected to another file and stop working soon
after access ends."""
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.auth.security import hash_password
from app.main import app
from app.models.enums import UserRole, VerificationStatus
from app.models.notification import Notification
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _verified(db, role, email, organization=False):
    c = TestClient(app)
    uid = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role}).json()["id"]
    c.put("/account/stakeholder", json={"type": "organization", "legal_name": "Org", "authorized": True} if organization else {"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    p = db.get(model, uid)
    p.verification_status = VerificationStatus.approved
    if role == "service_provider":
        p.company_name = email.split("@")[0]
        p.payment_override_active = True
    db.commit()
    return c


def _get(client, url):
    return client.get("/" + url.split("://", 1)[-1].split("/", 1)[-1])


def _files(owner, status="open", **extra):
    return owner.post(
        "/projects",
        data={"title": "Villa rewiring", "address": "Kaifan", "description": "Rewire a villa.", "bid_deadline": _when(10), "status": status, **extra},
        files=[("drawings", ("single-line.pdf", b"%PDF-sld", "application/pdf")), ("drawings", ("boq.xlsx", b"PK-boq", "application/vnd.ms-excel"))],
    ).json()["id"]


def test_providers_get_the_current_documents_named_and_viewable(db):
    owner = _verified(db, "owner", "owner@example.com")
    a, b = _verified(db, "service_provider", "a@example.com"), _verified(db, "service_provider", "b@example.com")
    pid = _files(owner)
    for client in (a, b):  # 1/11. every entitled provider, independently
        docs = {d["file_name"]: d for d in client.get(f"/projects/{pid}").json()["drawings"]}
        assert set(docs) == {"single-line.pdf", "boq.xlsx"}
        pdf, boq = _get(client, docs["single-line.pdf"]["url"]), _get(client, docs["boq.xlsx"]["url"])
        assert pdf.content == b"%PDF-sld" and pdf.headers["content-type"] == "application/pdf" and pdf.headers["content-disposition"].startswith("inline")
        assert 'filename="single-line.pdf"' in pdf.headers["content-disposition"] and pdf.headers["x-content-type-options"] == "nosniff"
        assert boq.content == b"PK-boq" and boq.headers["content-disposition"].startswith('attachment; filename="boq.xlsx"')
    # Links are short-lived: an hour at most.
    exp = int(parse_qs(urlparse(docs["boq.xlsx"]["url"]).query)["exp"][0])
    assert exp - time.time() <= 3600 + 5


def test_no_link_or_endpoint_reaches_a_file_it_shouldnt(db):
    owner = _verified(db, "owner", "owner@example.com")
    other_owner = _verified(db, "owner", "other@example.com")
    sp = _verified(db, "service_provider", "a@example.com")
    pid, other = _files(owner), _files(other_owner)
    url = sp.get(f"/projects/{pid}").json()["drawings"][0]["url"]
    other_url = sp.get(f"/projects/{other}").json()["drawings"][0]["url"]
    # 4/8. Another requirement's file by changing the path, the name, the expiry or the signature: refused.
    assert _get(sp, url.replace(pid, other)).status_code == 403
    assert _get(sp, url.split("&name=")[0] + "&name=boq.xlsx").status_code == 403
    assert _get(sp, url.split("&name=")[0]).status_code == 403  # dropping the signed name
    q = parse_qs(urlparse(url).query)
    assert _get(sp, url.replace(f"exp={q['exp'][0]}", f"exp={int(q['exp'][0]) + 86400}")).status_code == 403
    sig = q["sig"][0]
    forged = sig[:-1] + ("1" if sig[-1] == "0" else "0")  # always a different signature
    assert _get(sp, url.replace(sig, forged)).status_code == 403
    assert _get(sp, other_url).status_code == 200  # (its own link works)
    # 3/6. A draft's documents: the owner side only.
    draft = _files(owner, status="draft")
    assert sp.get(f"/projects/{draft}").status_code == 404
    for path in ("drawings-zip", "drawings/history", "versions/0"):
        assert sp.get(f"/projects/{draft}/{path}").status_code == 404, path
    own = owner.get(f"/projects/{draft}").json()["drawings"][0]["url"]
    assert _get(owner, own).status_code == 200
    assert other_owner.get(f"/projects/{draft}/drawings/history").status_code == 404
    # 10. File validation stays: an executable is refused, nothing stored.
    r = owner.post(f"/projects/{draft}/drawings", files=[("drawings", ("setup.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 400 and len(owner.get(f"/projects/{draft}").json()["drawings"]) == 2


def test_who_may_open_documents_follows_eligibility_and_lifecycle(db):
    owner = _verified(db, "owner", "owner@example.com")
    bidder, watcher = _verified(db, "service_provider", "a@example.com"), _verified(db, "service_provider", "b@example.com")
    pid = _files(owner)
    restricted = owner.post("/projects", data={"title": "Substation", "address": "x", "description": "HV works.", "bid_deadline": _when(9)}, files=[("drawings", ("hv.pdf", b"%PDF-hv", "application/pdf"))]).json()["id"]
    owner.put(f"/projects/{restricted}/eligibility", json={"provider_type": "organization"})
    owner.post(f"/owner/projects/{restricted}/publish")
    # 2. Not eligible: no documents by any route.
    for path in ("", "/drawings-zip", "/drawings/history", "/versions/0"):
        assert watcher.get(f"/projects/{restricted}{path}").status_code == 404, path
    bidder.post(f"/projects/{pid}/offers", json={"amount": "900"})
    db.add(User(email="admin@example.com", password_hash=hash_password("adminpass123"), role=UserRole.admin, full_name="A"))
    db.commit()
    admin = TestClient(app)
    admin.post("/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    # 9. Hidden by U-Tender: nobody but its owner side.
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True})
    for client in (bidder, watcher):
        assert client.get(f"/projects/{pid}/drawings-zip").status_code == 404 and client.get(f"/projects/{pid}/drawings/history").status_code == 404
    admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": False})
    # Ended: the bidder keeps its documents (history kept, nothing deleted); others don't get them.
    owner.post(f"/owner/projects/{pid}/cancel", json={"reason": "not_needed"})
    assert bidder.get(f"/projects/{pid}/drawings-zip").status_code == 200
    assert len(bidder.get(f"/projects/{pid}").json()["drawings"]) == 2
    assert watcher.get(f"/projects/{pid}/drawings-zip").status_code == 404


def test_a_replaced_document_is_clear_and_the_earlier_offer_stays_with_the_original(db):
    owner = _verified(db, "owner", "owner@example.com")
    bidder, watcher = _verified(db, "service_provider", "a@example.com"), _verified(db, "service_provider", "b@example.com")
    pid = _files(owner)
    bidder.post(f"/projects/{pid}/offers", json={"amount": "900"})
    watcher.post(f"/projects/{pid}/clarifications", json={"question": "Is the DB board included?"})
    # 5. The owner replaces the single-line diagram.
    assert owner.post(f"/projects/{pid}/drawings", files=[("drawings", ("single-line.pdf", b"%PDF-sld-v2", "application/pdf"))]).status_code == 200
    current = {d["file_name"]: d for d in bidder.get(f"/projects/{pid}").json()["drawings"]}
    assert current["single-line.pdf"]["revision"] == 2 and _get(bidder, current["single-line.pdf"]["url"]).content == b"%PDF-sld-v2"
    # Recorded as a material change, with what was replaced; those involved are told.
    amendment = bidder.get(f"/projects/{pid}/amendments").json()[-1]
    assert amendment["material"] and amendment["changes"]["documents"]["replaced"] == ["single-line.pdf"]
    told = {n.user_id for n in db.query(Notification).filter(Notification.type == "tender_amendment")}
    assert len(told) == 2  # the bidder (review your offer) and the provider who asked about it
    # 6/7. The earlier offer stays tied to the version -- and the file -- it was priced on.
    offer_version = bidder.get(f"/projects/{pid}/offers/mine").json()["based_on_material_revision"]
    then = {d["file_name"]: d for d in bidder.get(f"/projects/{pid}/versions/{offer_version}").json()["documents"]}
    assert then["single-line.pdf"]["revision"] == 1 and not then["single-line.pdf"]["is_current"]
    assert _get(bidder, then["single-line.pdf"]["url"]).content == b"%PDF-sld"
    history = [(d["file_name"], d["revision"], d["is_current"]) for d in bidder.get(f"/projects/{pid}/drawings/history").json()]
    assert ("single-line.pdf", 1, False) in history and ("single-line.pdf", 2, True) in history

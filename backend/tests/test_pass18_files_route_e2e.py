"""PASS 18 (cont.) — end-to-end acceptance: a real drawing uploaded through
the actual FastAPI app, fetched back through the real /files route (local
backend), confirming the whole chain (upload -> signed_url() -> HMAC verify
-> serve) works together, not just the Storage class in isolation."""
from datetime import datetime, timedelta
import app.db as db_module  # noqa: E402
from fastapi.testclient import TestClient
from app.main import app


def test_pass18_files_route_e2e():
    results = []


    def check(name, cond):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL") + " - " + name)


    owner_client = TestClient(app)
    _owner_signup_r = owner_client.post("/auth/signup", json={"email": "owner1@example.com", "password": "password123", "full_name": "Owner", "role": "owner"})
    from app.models.owner import OwnerProfile as _OwnerProfile
    from app.models.enums import VerificationStatus as _OwnerVerificationStatus
    _owner_approve_db = db_module.SessionLocal()
    _owner_approve_db.get(_OwnerProfile, _owner_signup_r.json()['id']).verification_status = _OwnerVerificationStatus.approved
    _owner_approve_db.commit()

    future = (datetime.utcnow() + timedelta(days=7)).isoformat()
    r = owner_client.post(
        "/projects",
        data={"title": "Real file round trip", "address": "1 Main St", "bid_deadline": future, "status": "open"},
        files={"drawings": ("plan.pdf", b"real PDF bytes here", "application/pdf")},
    )
    check("project with a drawing created", r.status_code == 201)
    drawing = r.json()["drawings"][0]
    url = drawing["url"]
    check("signed url returned for the uploaded drawing", url and "/files/project-drawings/" in url)

    # Fetch it through the actual /files route, same as a browser would.
    path = url.split(owner_client.base_url.__str__())[-1] if str(owner_client.base_url) in url else url.replace("http://localhost:8000", "")
    r = owner_client.get(path)
    check("fetching the signed URL through the real /files route returns 200", r.status_code == 200)
    check("content served matches exactly what was uploaded", r.content == b"real PDF bytes here")

    # Tamper with the signature -> rejected.
    tampered = path.rsplit("sig=", 1)[0] + "sig=0000000000000000000000000000000000000000000000000000000000000000"
    r = owner_client.get(tampered)
    check("a tampered signature is rejected (403)", r.status_code == 403)

    # Tamper with the key (path traversal attempt through the public route itself).
    traversal_path = path.split("?")[0].rsplit("/", 1)[0] + "/../../../etc/passwd?" + path.split("?", 1)[1]
    r = owner_client.get(traversal_path)
    check("a path-traversal attempt through the public /files route does not return arbitrary file content", r.status_code in (403, 404))

    # An expired link (exp in the past) is rejected even with a technically-correct-looking signature.
    import time
    from app.services.storage import LocalFileStorage

    bucket, key = "project-drawings", drawing["id"]  # doesn't need to be the real key for this check
    expired_exp = int(time.time()) - 10
    expired_sig = LocalFileStorage._sign("project-drawings", "some/key.pdf", expired_exp)
    r = owner_client.get(f"/files/project-drawings/some/key.pdf?exp={expired_exp}&sig={expired_sig}")
    check("an expired (but correctly signed) link is rejected", r.status_code == 403)

    # A service provider with no access to this project cannot even discover the URL
    # (separate from the signed-URL mechanism) — the project detail endpoint
    # itself gates it, verified elsewhere; here we only confirm the /files
    # route's OWN defenses (signature + expiry) hold regardless of who calls it,
    # since a leaked URL is the realistic threat model for a signed link.
    anon_fetch = TestClient(app)  # no auth cookie at all
    r = anon_fetch.get(path)
    check("a valid signed URL works even for a client with NO auth cookie (by design — that's what 'signed' means)", r.status_code == 200)


    failed = [n for n, ok in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    assert not failed, "FAILED: " + str(failed)

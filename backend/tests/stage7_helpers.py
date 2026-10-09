"""Shared test helpers: put an awarded requirement's agreement in force, and
drive its transaction to the completed state (Stage 7.11), through the real API."""
from app.routers.agreements import kuwait_today


def put_in_force(owner, provider, project_id: str, effective=None) -> dict:
    """Batch A: the owner sets the effective date, the provider confirms the
    terms, the owner puts the agreement in force."""
    base = f"/projects/{project_id}/agreement"

    def v(client):
        return {"If-Match": str(client.get(base).json()["version"])}

    when = (effective or kuwait_today()).isoformat()
    assert owner.patch(base, json={"effective_date": when}, headers=v(owner)).status_code == 200
    assert provider.post(f"{base}/confirm", headers=v(provider)).status_code == 200
    r = owner.post(f"{base}/activate", headers=v(owner))
    assert r.status_code == 200 and r.json()["status"] == "active", r.text
    return r.json()


def complete_transaction(owner, provider, project_id: str) -> dict:
    base = f"/projects/{project_id}/agreement"

    def v(client):
        return {"If-Match": str(client.get(base).json()["version"])}

    put_in_force(owner, provider, project_id)
    assert provider.post(f"{base}/start-work", json={}, headers=v(provider)).status_code == 200
    assert provider.post(f"{base}/completion/submit", json={}, headers=v(provider)).status_code == 200
    r = owner.post(f"{base}/completion/accept", json={}, headers=v(owner))
    assert r.status_code == 200 and r.json()["status"] == "completed", r.text
    return r.json()

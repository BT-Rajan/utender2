"""Shared test helper: drive an awarded requirement's transaction to its
completed state (Stage 7.11) through the real API."""
from datetime import date, timedelta


def complete_transaction(owner, provider, project_id: str) -> dict:
    base = f"/projects/{project_id}/agreement"

    def v(client):
        return {"If-Match": str(client.get(base).json()["version"])}

    assert owner.patch(base, json={"effective_date": (date.today() + timedelta(days=1)).isoformat()}, headers=v(owner)).status_code == 200
    assert owner.post(f"{base}/activate", headers=v(owner)).status_code == 200
    assert provider.post(f"{base}/start-work", json={}, headers=v(provider)).status_code == 200
    assert provider.post(f"{base}/completion/submit", json={}, headers=v(provider)).status_code == 200
    r = owner.post(f"{base}/completion/accept", json={}, headers=v(owner))
    assert r.status_code == 200 and r.json()["status"] == "completed", r.text
    return r.json()

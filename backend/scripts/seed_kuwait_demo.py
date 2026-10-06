"""Seeds a running U-Tender instance with realistic Kuwait-flavored demo
data: owners, service providers, projects, and offers covering every lifecycle
state and admin-moderation feature built into the app, so there's
something real to click through immediately after a deploy.

Drives the actual HTTP API (not direct DB writes) -- the same approach
already proven by this project's live smoke tests -- so every row respects
the app's own business rules exactly (revision counters, tender-type
locking, the verification gate, etc.) instead of being hand-crafted and
potentially inconsistent.

Usage (run from anywhere, needs `requests` -- already a transitive
dependency of this project's own tooling, or `pip install requests`):

    python seed_kuwait_demo.py --api-url http://localhost:8000 \\
        --admin-email you@example.com --admin-password 'yourpassword'

Requires an admin account to already exist (see the README's "Create your
first admin" section) -- this script only ever logs in as one, it never
creates one, since admin signup is intentionally not self-serve.

Safe to run more than once for the accounts themselves (an email that
already exists is logged into instead of re-registered), but NOT for
projects/offers -- those have no natural unique key to dedupe against, so
re-running creates a second batch of them. Intended to run once against a
database that doesn't already have this demo data in it.
"""
import argparse
import sys
import time
from datetime import datetime, timedelta

import requests

PASSWORD = "Kuwait#2026"

OWNERS = [
    {"email": "owner.alsabah@example.com", "full_name": "Mohammed Al-Sabah", "approve": True},
    {"email": "owner.alrashidi@example.com", "full_name": "Fahad Al-Rashidi", "approve": True},
    {"email": "owner.alazmi@example.com", "full_name": "Yousef Al-Azmi", "approve": True},
    {"email": "owner.almutairi@example.com", "full_name": "Sara Al-Mutairi", "approve": False},  # left pending
]

SERVICE_PROVIDERS = [
    {
        "email": "service_provider.diyar@example.com",
        "full_name": "Ahmad Al-Fadhli",
        "company_name": "Al Diyar General Trading & Contracting Co. W.L.L.",
        "primary_trade": "General Contracting",
        "service_area": "Kuwait City, Hawally, Salmiya",
        "status": "active",
    },
    {
        "email": "service_provider.gulfmep@example.com",
        "full_name": "Bader Al-Enezi",
        "company_name": "Gulf Coast MEP Contracting Co.",
        "primary_trade": "MEP (Mechanical/Electrical/Plumbing)",
        "service_area": "Fintas, Mangaf, Ahmadi",
        "status": "active",
    },
    {
        "email": "service_provider.desertrose@example.com",
        "full_name": "Talal Al-Shammari",
        "company_name": "Desert Rose Landscaping & Civil Works",
        "primary_trade": "Landscaping",
        "service_area": "Mishref, Surra, Qortuba",
        "status": "active",
    },
    {
        "email": "service_provider.manara@example.com",
        "full_name": "Nasser Al-Otaibi",
        "company_name": "Al Manara Finishing & Interiors",
        "primary_trade": "Finishing & Interior Fit-Out",
        "service_area": "Jabriya, Salwa, Rumaithiya",
        "status": "active",
    },
    {
        "email": "service_provider.bahar@example.com",
        "full_name": "Khaled Al-Dosari",
        "company_name": "Al Bahar Interiors W.L.L.",
        "primary_trade": "Finishing & Interior Fit-Out",
        "service_area": "Sharq, Kuwait City",
        "status": "pending",  # left pending for the admin review queue
    },
    {
        "email": "service_provider.national@example.com",
        "full_name": "Salem Al-Kandari",
        "company_name": "National Construction Group",
        "primary_trade": "Civil Works",
        "service_area": "Jahra, Sabah Al-Salem",
        "status": "suspended",  # approved, then suspended -- demos that state
    },
]

FAKE_PDF = b"%PDF-1.4\n%demo document for seed data\n"


def log(msg: str) -> None:
    print(f"  {msg}")


def step(msg: str) -> None:
    print(f"\n==> {msg}")


def expect_ok(r: requests.Response, context: str) -> requests.Response:
    """A silent 4xx/5xx here would otherwise look identical to success --
    the calling step's own log line still prints, and nothing downstream
    necessarily fails outright (e.g. a follow-up "get the review" call
    just finds nothing, rather than erroring). Every mutating call in the
    lifecycle/admin-moderation sections goes through this instead of a
    bare .post()/.patch(), so a real failure stops the script immediately
    with the actual response body instead of finishing "successfully"
    with silently missing data (caught exactly this way once already,
    for the review submission below)."""
    if not r.ok:
        raise RuntimeError(f"{context} failed: {r.status_code} {r.text}")
    return r


class Client:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def post(self, path: str, **kwargs):
        r = self.session.post(self._url(path), **kwargs)
        return r

    def get(self, path: str, **kwargs):
        return self.session.get(self._url(path), **kwargs)

    def patch(self, path: str, **kwargs):
        return self.session.patch(self._url(path), **kwargs)

    def login(self, email: str, password: str) -> dict:
        r = self.post("/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        return r.json()


def signup_or_login(base_url: str, email: str, full_name: str, role: str, company_name: str | None = None) -> Client:
    client = Client(base_url)
    payload = {"email": email, "password": PASSWORD, "full_name": full_name, "role": role}
    if company_name:
        payload["company_name"] = company_name
    r = client.post("/auth/signup", json=payload)
    if r.status_code == 201:
        log(f"signed up {email}")
        return client
    if r.status_code == 400 and "already" in r.text.lower():
        client.login(email, PASSWORD)
        log(f"{email} already existed -- logged in instead")
        return client
    r.raise_for_status()
    return client


def upload_and_submit(client: Client, requirements_path: str, upload_path_tmpl: str, submit_path: str, submit_payload: dict | None = None) -> None:
    r = client.get(requirements_path)
    r.raise_for_status()
    for req in r.json():
        expect_ok(
            client.post(upload_path_tmpl.format(id=req["id"]), files={"file": ("doc.pdf", FAKE_PDF, "application/pdf")}),
            f"upload document for requirement {req['name']}",
        )
    expect_ok(client.post(submit_path, json=submit_payload or {}), f"submit for review ({submit_path})")


def approve_all_documents(admin: Client, entity_id: str, list_path: str, review_path: str, id_field: str) -> None:
    r = admin.get(list_path)
    r.raise_for_status()
    docs = r.json()["documents"] if isinstance(r.json(), dict) else r.json()
    for d in docs:
        expect_ok(
            admin.post(review_path, json={id_field: entity_id, "requirement_id": d["requirement_id"], "decision": "approved"}),
            f"approve document {d['requirement_id']} for {entity_id}",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    admin = Client(args.api_url)
    try:
        admin.login(args.admin_email, args.admin_password)
    except requests.HTTPError:
        print(f"Could not log in as {args.admin_email} -- check the email/password and that {args.api_url} is reachable.")
        sys.exit(1)
    log(f"logged in as admin ({args.admin_email})")

    step("ServiceProvider document requirements")
    existing = {r["name"] for r in admin.get("/admin/requirements").json()}
    for name, desc in [
        ("Commercial License", "Kuwait Municipality commercial license for the contracting company."),
        ("Chamber of Commerce Certificate", "Kuwait Chamber of Commerce and Industry membership certificate."),
    ]:
        if name not in existing:
            expect_ok(
                admin.post("/admin/requirements", json={"name": name, "description": desc, "is_required": True, "applies_to": "service_provider"}),
                f"add requirement {name}",
            )
            log(f"added service provider requirement: {name}")
        else:
            log(f"requirement already exists: {name}")

    step("Owners")
    owner_clients: dict[str, Client] = {}
    for o in OWNERS:
        c = signup_or_login(args.api_url, o["email"], o["full_name"], "owner")
        owner_clients[o["email"]] = c
        upload_and_submit(c, "/owner/requirements", "/owner/documents/{id}/upload", "/owner/submit-for-review")
        if o["approve"]:
            owner_id = c.get("/auth/me").json()["id"]
            approve_all_documents(admin, owner_id, f"/admin/owners/{owner_id}", "/admin/review/owner-documents", "owner_id")
            expect_ok(admin.post(f"/admin/review/owners/{owner_id}/approve"), f"approve owner {o['full_name']}")
            log(f"approved owner {o['full_name']}")
        else:
            log(f"left {o['full_name']} pending review (for the admin queue)")

    step("ServiceProviders")
    service_provider_clients: dict[str, Client] = {}
    for cinfo in SERVICE_PROVIDERS:
        c = signup_or_login(args.api_url, cinfo["email"], cinfo["full_name"], "service_provider", cinfo["company_name"])
        service_provider_clients[cinfo["email"]] = c
        service_provider_id = c.get("/auth/me").json()["id"]
        upload_and_submit(
            c, "/service-provider/requirements", "/service-provider/documents/{id}/upload", "/service-provider/submit-for-review",
            submit_payload={"company_name": cinfo["company_name"]},
        )
        if cinfo["status"] in ("active", "suspended"):
            approve_all_documents(admin, service_provider_id, f"/admin/service-providers/{service_provider_id}", "/admin/review/documents", "service_provider_id")
            expect_ok(admin.post(f"/admin/review/service-providers/{service_provider_id}/approve"), f"approve service provider {cinfo['company_name']}")
            expect_ok(
                admin.post(f"/admin/service-providers/{service_provider_id}/payment-override", json={"reason": "Kuwait demo dataset -- marketplace access without a real subscription."}),
                f"grant payment override to {cinfo['company_name']}",
            )
            expect_ok(
                admin.patch(
                    f"/admin/service-providers/{service_provider_id}",
                    json={
                        "company_name": cinfo["company_name"],
                        "license_number": None,
                        "primary_trade": cinfo["primary_trade"],
                        "service_area": cinfo["service_area"],
                    },
                ),
                f"update service provider profile for {cinfo['company_name']}",
            )
            log(f"approved + activated service provider {cinfo['company_name']}")
            if cinfo["status"] == "suspended":
                expect_ok(admin.post(f"/admin/service-providers/{service_provider_id}/suspend", json={"suspended": True}), f"suspend service provider {cinfo['company_name']}")
                log(f"suspended service provider {cinfo['company_name']} (demo state)")
        else:
            log(f"left {cinfo['company_name']} pending review (for the admin queue)")

    def future(days: int) -> str:
        return (datetime.utcnow() + timedelta(days=days)).isoformat()

    owner_a = owner_clients[OWNERS[0]["email"]]  # Al-Sabah
    owner_b = owner_clients[OWNERS[1]["email"]]  # Al-Rashidi
    owner_c = owner_clients[OWNERS[2]["email"]]  # Al-Azmi

    c_diyar = service_provider_clients["service_provider.diyar@example.com"]
    c_gulfmep = service_provider_clients["service_provider.gulfmep@example.com"]
    c_desertrose = service_provider_clients["service_provider.desertrose@example.com"]
    c_manara = service_provider_clients["service_provider.manara@example.com"]

    def create_project(owner: Client, title: str, address: str, description: str, trade: str, days: int, tender_type: str = "owner_visible", status: str = "open") -> str:
        r = owner.post(
            "/projects",
            data={
                "title": title,
                "address": address,
                "description": description,
                "trade": trade,
                "bid_deadline": future(days),
                "tender_type": tender_type,
                "status": status,
            },
        )
        r.raise_for_status()
        return r.json()["id"]

    step("Projects")

    p_villa = create_project(
        owner_a, "Villa Renovation — Block 4, Salmiya", "Block 4, Street 12, Salmiya, Kuwait",
        "Full interior renovation of a 2-floor villa: flooring, painting, and kitchen remodel.",
        "Finishing & Interior Fit-Out", 12,
    )
    log("open (owner-visible): Villa Renovation — Salmiya")

    p_majlis = create_project(
        owner_b, "New Majlis Construction — Jabriya", "Plot 7, Block 9, Jabriya, Kuwait",
        "Construction of a new majlis extension, approx. 120 sqm, including AC ducting and electrical.",
        "General Contracting", 14, tender_type="sealed",
    )
    log("open (sealed): New Majlis Construction — Jabriya")

    p_mosque = create_project(
        owner_c, "Mosque AC System Upgrade — Fintas", "Al-Fintas District, near Block 3, Kuwait",
        "Replacement of the central AC system serving the main prayer hall and ablution area.",
        "MEP (Mechanical/Electrical/Plumbing)", 7,
    )
    log("will move to under_evaluation: Mosque AC System Upgrade — Fintas")

    p_facade = create_project(
        owner_a, "Commercial Building Facade — Sharq", "Fahad Al-Salem Street, Sharq, Kuwait City",
        "Aluminum and glass facade replacement for a 6-story commercial building.",
        "Finishing & Interior Fit-Out", 10,
    )
    log("will be awarded: Commercial Building Facade — Sharq")

    p_compound = create_project(
        owner_b, "Compound Landscaping — Mishref", "Compound 14, Mishref, Kuwait",
        "Landscaping and irrigation system for a private residential compound garden.",
        "Landscaping", 9,
    )
    log("will end in no_award: Compound Landscaping — Mishref")

    p_warehouse = create_project(
        owner_c, "Warehouse Extension — Shuwaikh Industrial", "Shuwaikh Industrial Area, Plot 22, Kuwait",
        "Steel-frame extension to an existing warehouse, approx. 400 sqm.",
        "Civil Works", 20, status="draft",
    )
    log("draft (never published): Warehouse Extension — Shuwaikh Industrial")

    p_diwaniya = create_project(
        owner_a, "Diwaniya Renovation — Andalous", "Block 2, Andalous, Kuwait",
        "Renovation of a traditional diwaniya: new seating area, lighting, and exterior paint.",
        "General Contracting", 11,
    )
    log("open, will be admin-suspended (demo state): Diwaniya Renovation — Andalous")

    def submit_offer(service_provider: Client, project_id: str, amount: str, timeline: str, message: str) -> str:
        r = service_provider.post(f"/projects/{project_id}/offers", json={"amount": amount, "timeline_estimate": timeline, "message": message})
        r.raise_for_status()
        return r.json()["id"]

    step("Offers")

    submit_offer(c_manara, p_villa, "8500.000", "3 weeks", "Includes all materials and a 1-year workmanship warranty.")
    submit_offer(c_diyar, p_villa, "9200.000", "4 weeks", "Premium fittings, flexible payment in 2 installments.")
    log("2 offers on Villa Renovation — Salmiya")

    submit_offer(c_diyar, p_majlis, "22000.000", "6 weeks", "Turnkey majlis construction including AC and electrical.")
    submit_offer(c_desertrose, p_majlis, "24500.000", "7 weeks", "Includes exterior landscaping around the new majlis.")
    log("2 offers on New Majlis Construction — Jabriya (sealed)")

    o_mosque_1 = submit_offer(c_gulfmep, p_mosque, "6800.000", "10 days", "Full system replacement, 2-year parts warranty.")
    submit_offer(c_diyar, p_mosque, "7400.000", "2 weeks", "Includes ducting inspection and minor civil works.")
    log("2 offers on Mosque AC System Upgrade — Fintas")

    o_facade_winner = submit_offer(c_manara, p_facade, "45000.000", "8 weeks", "Aluminum composite panels, structural glazing, safety certification included.")
    submit_offer(c_diyar, p_facade, "48500.000", "10 weeks", "Includes scaffolding and full site safety management.")
    log("2 offers on Commercial Building Facade — Sharq")

    submit_offer(c_desertrose, p_compound, "5200.000", "2 weeks", "Drip irrigation, native plants suited to Kuwait's climate.")
    log("1 offer on Compound Landscaping — Mishref")

    submit_offer(c_diyar, p_diwaniya, "12000.000", "3 weeks", "Modern diwaniya seating and full electrical rewiring.")
    submit_offer(c_manara, p_diwaniya, "13500.000", "4 weeks", "Premium interior finish with custom majlis seating.")
    log("2 offers on Diwaniya Renovation — Andalous")

    step("Advancing lifecycle states")

    expect_ok(owner_c.post(f"/owner/projects/{p_mosque}/close"), "close mosque project")
    expect_ok(owner_c.post(f"/owner/projects/{p_mosque}/start-evaluation"), "start evaluation on mosque project")
    log("Mosque AC System Upgrade — now under_evaluation")

    expect_ok(owner_a.post(f"/owner/projects/{p_facade}/close"), "close facade project")
    expect_ok(owner_a.post(f"/owner/projects/{p_facade}/offers/{o_facade_winner}/approve"), "award facade project")
    manara_id = c_manara.get("/auth/me").json()["id"]
    expect_ok(
        owner_a.post("/owner/reviews", json={"project_id": p_facade, "service_provider_id": manara_id, "rating": 5, "comment": "Excellent work, finished ahead of schedule."}),
        "submit review for facade project",
    )
    log("Commercial Building Facade — awarded to Al Manara Finishing & Interiors, review submitted")

    expect_ok(owner_b.post(f"/owner/projects/{p_compound}/close"), "close compound project")
    expect_ok(owner_b.post(f"/owner/projects/{p_compound}/no-award"), "mark compound project no-award")
    log("Compound Landscaping — marked no_award")

    step("Admin moderation demo state")
    expect_ok(admin.post(f"/admin/projects/{p_diwaniya}/suspend", json={"suspended": True}), "suspend diwaniya project")
    log("Diwaniya Renovation — suspended by admin (hidden from service provider feed)")
    expect_ok(admin.post(f"/admin/offers/{o_mosque_1}/suspend", json={"suspended": True}), "suspend mosque offer")
    log("Gulf Coast MEP's offer on the Mosque project — suspended by admin")

    step("Done")
    print()
    print("Kuwait demo dataset created. Everyone's password is: " + PASSWORD)
    print()
    print("Sample logins:")
    print(f"  Owner (approved):      {OWNERS[0]['email']}")
    print(f"  Owner (pending):       {OWNERS[3]['email']}")
    print(f"  Service provider (active):   {SERVICE_PROVIDERS[0]['email']}")
    print(f"  Service provider (pending):  {SERVICE_PROVIDERS[4]['email']}")
    print(f"  Service provider (suspended):{SERVICE_PROVIDERS[5]['email']}")


if __name__ == "__main__":
    main()

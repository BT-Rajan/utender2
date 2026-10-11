#!/usr/bin/env python3
"""ONE-TIME stage-by-stage test data for U-Tender.

Creates exactly 11 accounts and ~17 tenders, placed so that every stage of the
app (verification, requirement drafting, discovery, offers, evaluation, award,
agreement/execution, completion, reviews, admin moderation) has data sitting
in it, ready to be tested.

    1 admin
    2 owners      (1 individual, 1 organization)
    4 providers   (staff: 2 / 1 / 0 / 1  ->  4 staff accounts)
    ---
    11 users

NOT part of application setup: nothing in deploy.sh, alembic or the README
calls this. Run it once, by hand, against a TEST database.

How it works
------------
* Everything is created through the real HTTP API, so every row obeys the
  app's own business rules (revision counters, verification gate, sealed bids,
  agreement versions, ...). Only two things are done directly against the
  database, because the API deliberately offers no way to do them:
    1. creating the admin account (admin sign-up is not self-serve), and
    2. issuing the e-mail verification token (the real token is only ever
       e-mailed). The token is then redeemed through POST /auth/verify-email.
  Because of (1) and (2) the script must be run from a machine that has the
  backend's `.env` (so it can reach the same database as the API).

Usage (from the repo root, with the backend virtualenv active):

    cd backend
    python ../stage-test-data/seed_stage_test_data.py --api-url http://localhost:8000

Afterwards read stage-test-data/TEST-DATA-GUIDE.md and (if you want ids)
stage-test-data/last_run_manifest.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"
if not (BACKEND / "app").is_dir():
    sys.exit(f"Cannot find the backend at {BACKEND}. Keep this script inside the repo's stage-test-data/ folder.")
os.chdir(BACKEND)  # so the backend's .env is the one read
sys.path.insert(0, str(BACKEND))

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("Needs `requests`:  pip install requests")

# ----------------------------------------------------------------------------
# The cast. Edit here (and only here) if you want different names/emails.
# ----------------------------------------------------------------------------
PASSWORD = "UTender#Test2026"
DOMAIN = "utender-test.example"  # reserved TLD: no real mailbox, nothing can be delivered by accident


def em(local: str) -> str:
    return f"{local}@{DOMAIN}"


ADMIN = {"email": em("admin"), "name": "Test Admin"}

OWNERS = {
    "O1": {"email": em("owner.individual"), "name": "Fahad Al-Rashidi", "org": None},
    "O2": {"email": em("owner.org"), "name": "Noura Al-Sabah", "org": "Gulf Holdings Real Estate W.L.L.", "position": "General Manager"},
}

# state: active = approved + payment override | unpaid = approved, no payment | pending = documents submitted, awaiting admin
PROVIDERS = {
    "P1": {"email": em("provider.diyar"), "name": "Ahmad Al-Fadhli", "org": "Al Diyar General Contracting Co. W.L.L.", "position": "Managing Partner",
           "state": "active", "categories": ["General Contracting", "Finishing & Interior Fit-Out"], "governorates": ["hawalli", "capital"],
           "has_iso": True,
           "staff": [("diyar.staff1", "Mariam Al-Kandari", "Site Engineer"), ("diyar.staff2", "Yousef Al-Mutairi", "Estimator")]},
    "P2": {"email": em("provider.gulfmep"), "name": "Bader Al-Enezi", "org": "Gulf Coast MEP Contracting Co.", "position": "Director",
           "state": "unpaid", "categories": ["MEP Works"], "governorates": ["ahmadi", "hawalli"],
           "staff": [("gulfmep.staff1", "Dalal Al-Azmi", "MEP Coordinator")]},
    "P3": {"email": em("provider.freelance"), "name": "Talal Al-Shammari", "org": None,
           "state": "active", "categories": ["General Contracting", "Landscaping", "Civil Works"], "governorates": ["hawalli", "mubarak_al_kabeer", "capital"],
           "staff": []},
    "P4": {"email": em("provider.bahar"), "name": "Khaled Al-Dosari", "org": "Al Bahar Interiors W.L.L.", "position": "Owner",
           "state": "pending", "categories": ["Finishing & Interior Fit-Out"], "governorates": ["capital"],
           # signed up + e-mail verified + INVITED, but has NOT accepted the invitation (so you can test accepting it)
           "staff": [("bahar.staff1", "Reem Al-Dosari", "Designer")], "leave_invited": True},
}

CATEGORIES = ["General Contracting", "MEP Works", "Finishing & Interior Fit-Out", "Landscaping", "Civil Works"]

FAKE_PDF = b"%PDF-1.4\n%U-Tender stage test data (not a real document)\n"
DECL = "I have visited the site."


# ----------------------------------------------------------------------------
# Small HTTP helper
# ----------------------------------------------------------------------------
class Client:
    def __init__(self, base: str, label: str = ""):
        self.base = base.rstrip("/")
        self.label = label
        self.s = requests.Session()

    def _call(self, method: str, path: str, **kw) -> requests.Response:
        r = self.s.request(method, f"{self.base}{path}", timeout=60, **kw)
        return r

    get = lambda self, p, **k: self._call("GET", p, **k)
    post = lambda self, p, **k: self._call("POST", p, **k)
    put = lambda self, p, **k: self._call("PUT", p, **k)
    patch = lambda self, p, **k: self._call("PATCH", p, **k)
    delete = lambda self, p, **k: self._call("DELETE", p, **k)

    def must(self, r: requests.Response, what: str) -> requests.Response:
        if not r.ok:
            raise SystemExit(f"\n!! FAILED: {what}\n   as {self.label or '?'}: {r.request.method} {r.request.path_url} -> {r.status_code}\n   {r.text[:600]}\n")
        return r

    def j(self, method: str, path: str, what: str, **kw):
        return self.must(self._call(method, path, **kw), what).json()

    def allow_plain_http_cookies(self):
        """Auth cookies are marked Secure when the server's APP_URL is https; requests then
        refuses to send them over plain http (e.g. http://localhost:8000 on the server itself)."""
        for c in self.s.cookies:
            c.secure = False

    def login(self, email: str, password: str = PASSWORD):
        r = self.must(self.post("/auth/login", json={"email": email, "password": password}), f"log in {email}")
        self.allow_plain_http_cookies()
        return r.json()

    def me(self) -> dict:
        return self.j("GET", "/auth/me", "read /auth/me")


def say(msg: str = "", indent: int = 2):
    print(" " * indent + msg, flush=True)


def head(msg: str):
    print(f"\n==> {msg}", flush=True)


def future(days: float) -> str:
    return (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days)).replace(microsecond=0).isoformat()


# ----------------------------------------------------------------------------
# Direct-database helpers (the only two things the API cannot do)
# ----------------------------------------------------------------------------
def db_session():
    from app.db import SessionLocal
    return SessionLocal()


def db_user_exists(email: str) -> bool:
    from app.models.user import User
    with db_session() as db:
        return db.query(User.id).filter(User.email == email.lower()).first() is not None


def db_create_admin(email: str, name: str) -> None:
    from app.auth.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User
    with db_session() as db:
        db.add(User(email=email.lower(), password_hash=hash_password(PASSWORD), role=UserRole.admin, full_name=name, email_verified=True))
        db.commit()


def verify_email_via_api(c: Client, user_id: str, email: str):
    """Issue the e-mail verification token directly, then redeem it through the real endpoint."""
    from app.models.enums import AuthTokenType
    from app.services.auth_tokens import issue_token
    with db_session() as db:
        token = issue_token(db, user_id, AuthTokenType.email_verify)
    c.must(c.post("/auth/verify-email", json={"token": token}), f"verify e-mail for {email}")


# ----------------------------------------------------------------------------
# Cast construction
# ----------------------------------------------------------------------------
def signup(api: str, email: str, name: str, role: str) -> Client:
    c = Client(api, email)
    r = c.must(c.post("/auth/signup", json={"email": email, "password": PASSWORD, "full_name": name, "role": role}), f"sign up {email}")
    c.allow_plain_http_cookies()
    c.user_id = r.json()["id"]
    return c


def establish(c: Client, who: dict):
    if who.get("org"):
        c.must(c.put("/account/stakeholder", json={"type": "organization", "legal_name": who["org"], "position": who.get("position"), "authorized": True}),
               f"establish organization {who['org']}")
    else:
        c.must(c.put("/account/stakeholder", json={"type": "individual"}), f"establish individual {who['email']}")


def submit_verification(c: Client, role: str, who: dict, include_optional: bool = False):
    base = "/owner" if role == "owner" else "/service-provider"
    reqs = c.j("GET", f"{base}/requirements", "list requirements")
    for rq in reqs:
        if rq.get("is_required", True) or include_optional:
            c.must(c.post(f"{base}/documents/{rq['id']}/upload", files={"file": ("document.pdf", FAKE_PDF, "application/pdf")}),
                   f"upload '{rq['name']}' for {who['email']}")
    payload = {"company_name": who.get("org") or who["name"]} if role == "service_provider" else {}
    c.must(c.post(f"{base}/submit-for-review", json=payload), f"submit {who['email']} for review")


def admin_approve(admin: Client, role: str, uid: str):
    if role == "owner":
        detail = admin.j("GET", f"/admin/owners/{uid}", "read owner for review")
        for d in (detail["documents"] if isinstance(detail, dict) else detail):
            admin.must(admin.post("/admin/review/owner-documents", json={"owner_id": uid, "requirement_id": d["requirement_id"], "decision": "approved"}), "approve owner document")
        admin.must(admin.post(f"/admin/review/owners/{uid}/approve"), "approve owner")
    else:
        detail = admin.j("GET", f"/admin/service-providers/{uid}", "read provider for review")
        for d in (detail["documents"] if isinstance(detail, dict) else detail):
            if d.get("status") in ("pending",):
                admin.must(admin.post("/admin/review/documents", json={"service_provider_id": uid, "requirement_id": d["requirement_id"], "decision": "approved"}), "approve provider document")
        admin.must(admin.post(f"/admin/review/service-providers/{uid}/approve"), "approve provider")


def build_cast(api: str, admin: Client, cat_ids: dict[str, str]) -> dict:
    cast: dict = {"owners": {}, "providers": {}, "staff": {}, "invitations": {}}

    head("Owners")
    for key, o in OWNERS.items():
        c = signup(api, o["email"], o["name"], "owner")
        verify_email_via_api(c, c.user_id, o["email"])
        establish(c, o)
        submit_verification(c, "owner", o)
        admin_approve(admin, "owner", c.user_id)
        cast["owners"][key] = c
        say(f"{key}  {o['email']}  ({'organization: ' + o['org'] if o['org'] else 'individual'})  -> approved")

    head("Providers (and their staff)")
    for key, p in PROVIDERS.items():
        c = signup(api, p["email"], p["name"], "service_provider")
        verify_email_via_api(c, c.user_id, p["email"])
        establish(c, p)
        cast["providers"][key] = c
        # only P1 also supplies the optional ISO 9001 certificate (used by the 'qualification required' tender)
        submit_verification(c, "service_provider", p, include_optional=bool(p.get("has_iso")))
        c.must(c.put("/service-provider/services", json={"categories": [cat_ids[n] for n in p["categories"]], "governorates": p["governorates"]}), "declare services")

        if p["state"] in ("active", "unpaid"):
            admin_approve(admin, "service_provider", c.user_id)
            if p["state"] == "active":
                admin.must(admin.post(f"/admin/service-providers/{c.user_id}/payment-override", json={"reason": "Stage test data: marketplace access without a real subscription."}),
                           f"payment override for {key}")
        say(f"{key}  {p['email']}  ({'organization' if p['org'] else 'individual'})  state={p['state']}")

        # --- staff -----------------------------------------------------------
        for local, sname, position in p["staff"]:
            semail = em(local)
            s = signup(api, semail, sname, "service_provider")
            verify_email_via_api(s, s.user_id, semail)
            inv = c.j("POST", "/account/organization/invitations", f"invite {semail}", json={"email": semail, "position": position})
            token = inv["link"].rsplit("/", 1)[-1]
            if p.get("leave_invited"):
                cast["invitations"][semail] = {"link": inv["link"], "token": token, "organization": p["org"]}
                say(f"    staff {semail}  -> invited, NOT yet accepted")
            else:
                s.must(s.post(f"/account/invitations/{token}/accept"), f"{semail} accepts invitation")
                say(f"    staff {semail}  -> joined {p['org']}")
            cast["staff"][local] = s
    return cast


# ----------------------------------------------------------------------------
# Tender helpers
# ----------------------------------------------------------------------------
def resp_reqs(owner: Client, pid: str, *, approach=True, doc=True, decl=True):
    owner.must(owner.put(f"/projects/{pid}/response-requirements", json={
        "approach": "required" if approach else "optional",
        "completion_period": "optional",
        "documents": [{"name": "Method statement", "required": True}] if doc else [],
        "declarations": [DECL] if decl else [],
    }), "set response requirements")


GOV = {"hawalli": "Salmiya", "capital": "Sharq", "ahmadi": "Fintas", "mubarak_al_kabeer": "Mishref", "farwaniya": "Andalous", "jahra": "Jahra"}


def new_project(owner: Client, code: str, title: str, *, gov="hawalli", cat: str | None = None, desc: str | None = None, days=21, sealed=False,
                start: int | None = None, duration: int | None = None, cat_ids=None) -> str:
    data = {
        "title": f"[{code}] {title}",
        "address": f"Block {len(code) + 3}, Street 12, {GOV[gov]}, Kuwait",
        "governorate": gov, "area": GOV[gov],
        "bid_deadline": future(days),
        "tender_type": "sealed" if sealed else "owner_visible",
    }
    if desc:
        data["description"] = desc
    if cat and cat_ids:
        data["category_id"] = cat_ids[cat]
    if start is not None:
        data["expected_start_date"] = (date.today() + timedelta(days=start)).isoformat()
    if duration is not None:
        data["expected_duration_days"] = duration
    return owner.j("POST", "/projects", f"create [{code}]", data=data)["id"]


def publish(owner: Client, pid: str, code: str):
    owner.must(owner.post(f"/owner/projects/{pid}/publish"), f"publish [{code}]")


def open_tender(owner: Client, code: str, title: str, **kw) -> str:
    desc = kw.pop("desc", None) or f"{title}. Supply, install and commission as per the attached scope. Site visit recommended before pricing."
    pid = new_project(owner, code, title, desc=desc, **kw)
    resp_reqs(owner, pid)
    publish(owner, pid, code)
    return pid


def draft_offer(sp: Client, pid: str, amount: str, method: str, *, days=30, submit=True) -> str | None:
    sp.must(sp.post(f"/projects/{pid}/participate"), "start participating")
    sp.must(sp.put(f"/projects/{pid}/offers/draft", json={
        "amount": amount, "message": method, "assumptions": f"Assumes: {method}", "accepted_declarations": [DECL],
        "proposed_duration_days": days}), "save offer draft")
    sp.must(sp.post(f"/projects/{pid}/offers/documents", data={"label": "Method statement"}, files={"file": (f"method-{int(time.time()*1000)%100000}.pdf", FAKE_PDF, "application/pdf")}),
            "attach method statement")
    if not submit:
        return None
    return sp.j("POST", f"/projects/{pid}/offers/draft/submit", "submit offer")["id"]


def agreement(c: Client, pid: str) -> dict:
    return c.j("GET", f"/projects/{pid}/agreement", "read agreement")


def ver(c: Client, pid: str) -> dict:
    return {"If-Match": str(agreement(c, pid)["version"])}


def put_in_force(owner: Client, provider: Client, pid: str):
    from app.routers.agreements import kuwait_today
    base = f"/projects/{pid}/agreement"
    owner.must(owner.patch(base, json={"reference": f"PO-TEST-{pid[:6].upper()}", "effective_date": kuwait_today().isoformat()}, headers=ver(owner, pid)), "set agreement effective date")
    provider.must(provider.post(f"{base}/confirm", headers=ver(provider, pid)), "provider confirms agreement terms")
    owner.must(owner.post(f"{base}/activate", headers=ver(owner, pid)), "owner puts agreement in force")


def milestone(c: Client, pid: str, title: str) -> str:
    base = f"/projects/{pid}/agreement/milestones"
    ms = c.j("POST", base, f"add milestone '{title}'", json={"title": title, "due_date": (date.today() + timedelta(days=45)).isoformat()}, headers=ver(c, pid))["milestones"]
    return next(m["id"] for m in ms if m["title"] == title)


def mver(c: Client, pid: str, mid: str) -> dict:
    return {"If-Match": str(next(m for m in agreement(c, pid)["milestones"] if m["id"] == mid)["version"])}


def close_and_award(owner: Client, pid: str, offer_id: str, code: str):
    owner.must(owner.post(f"/owner/projects/{pid}/close"), f"close [{code}]")
    owner.must(owner.post(f"/owner/projects/{pid}/offers/{offer_id}/approve"), f"award [{code}]")


# ----------------------------------------------------------------------------
# The tenders, grouped by stage
# ----------------------------------------------------------------------------
def build_tenders(admin: Client, cast: dict, cat_ids: dict, qual_id: str | None) -> dict:
    O1, O2 = cast["owners"]["O1"], cast["owners"]["O2"]
    P1, P2, P3, P4 = (cast["providers"][k] for k in ("P1", "P2", "P3", "P4"))
    S1, S2 = cast["staff"]["diyar.staff1"], cast["staff"]["diyar.staff2"]
    T: dict[str, str] = {}

    head("STAGE 3 - owner builds a requirement (drafts)")
    T["T01"] = new_project(O1, "T01", "Warehouse Extension - Shuwaikh (barely started)", gov="capital", days=25)
    say("T01 draft, only title/location/deadline filled in (quality check should block publishing)")

    T["T02"] = pid = new_project(O2, "T02", "Majlis Extension - Jabriya (ready to publish)", gov="hawalli", cat="General Contracting", cat_ids=cat_ids, days=25, start=40, duration=90,
                                 desc="Construct a 120 sqm majlis extension: foundations, structure, block work, plaster, paint, electrical and AC ducting. "
                                      "Contractor to supply all labour and materials. Work to follow the attached drawings and Kuwait Municipality requirements.")
    O2.must(O2.put(f"/projects/{pid}/items", json={"pricing_basis": "per_item", "items": [
        {"description": "Foundations and structure", "quantity": "1", "unit": "lot", "specification": "Reinforced concrete, grade C30"},
        {"description": "Block work and plaster", "quantity": "420", "unit": "sqm"},
        {"description": "Electrical and AC ducting", "quantity": "1", "unit": "lot"}]}), "set priced items")
    resp_reqs(O2, pid)
    O2.must(O2.post(f"/projects/{pid}/drawings", files=[("drawings", ("majlis-plan.pdf", FAKE_PDF, "application/pdf"))], data={"category": "drawing", "is_required": "true"}), "attach drawing")
    O2.must(O2.put(f"/projects/{pid}/tender-rules", json={
        "tender_type": "owner_visible", "questions_allowed": True,
        "commercial_conditions": {"offer_validity_days": 60, "payment_stages": [{"milestone": "On mobilisation", "percent": 20}, {"milestone": "On structure completion", "percent": 50}, {"milestone": "On handover", "percent": 30}],
                                  "retention_percent": 5, "retention_months": 12, "warranty_months": 12},
        "bidder_instructions": "Include a programme in the method statement."}), "set tender rules")
    say("T02 draft, complete: per-item pricing, drawing, tender rules, response requirements (publish it yourself)")

    head("STAGE 3.15 / 4 - open requirements (discovery, eligibility, Q&A, amendments, pause)")
    T["T04"] = open_tender(O1, "T04", "Villa Renovation - Salmiya (clean slate)", gov="hawalli", cat="General Contracting", cat_ids=cat_ids, days=21, start=30, duration=60)
    say("T04 open, owner-visible, NO activity: use it for a first offer from scratch")

    T["T05"] = pid = new_project(O2, "T05", "Substation Fit-Out - Salmiya (organisations with ISO 9001 only)", gov="hawalli", cat="General Contracting", cat_ids=cat_ids, days=21,
                                 desc="Fit-out of a small substation building. Only organisations holding an ISO 9001 certificate and serving Hawalli may respond.")
    resp_reqs(O2, pid)
    O2.must(O2.put(f"/projects/{pid}/eligibility", json={"provider_type": "organization", "qualifications": [qual_id] if qual_id else [], "match_category": True, "match_governorate": True}),
            "set eligibility rules")
    publish(O2, pid, "T05")
    say("T05 open, eligibility rules: organisation + ISO 9001 + serves Hawalli + General Contracting (P1 qualifies; P3 individual, P2 unpaid do not)")

    T["T06"] = pid = open_tender(O1, "T06", "Mall Facade Cleaning System - Sharq (SEALED)", gov="capital", cat="General Contracting", cat_ids=cat_ids, days=14, sealed=True)
    o_p1 = draft_offer(P1, pid, "21500", "Rope-access cleaning, 6 visits per year")
    draft_offer(P3, pid, "19800", "Gondola cleaning, 4 visits per year")
    P1.must(P1.post(f"/projects/{pid}/offers", json={"amount": "20900", "message": "Rope-access cleaning, 6 visits per year (revised price)", "assumptions": "Water supplied by owner",
                                                    "accepted_declarations": [DECL], "proposed_duration_days": 30}, headers={"If-Match": "1"}), "revise P1 offer on T06")
    say("T06 open SEALED: P1 submitted then REVISED (rev 2), P3 submitted. Owner must not see amounts/identities until deadline")

    T["T07"] = pid = open_tender(O2, "T07", "Villa Rewiring - Hawalli (offer prepared by staff)", gov="hawalli", cat="General Contracting", cat_ids=cat_ids, days=18)
    draft_offer(S1, pid, "7400", "Full rewire, 40 points, new DB", submit=True)
    draft_offer(P3, pid, "6900", "Rewire with surface conduit", submit=False)
    P1.must(P1.put(f"/service-provider/saved/{T['T04']}"), "save T04 for P1")
    say("T07 open owner-visible: offer for P1 was created+submitted by STAFF member diyar.staff1 (shared with org); P3 has an unsent DRAFT offer; P1 has T04 saved")

    T["T08"] = pid = open_tender(O1, "T08", "Mosque AC Upgrade - Fintas (Q&A + material amendment)", gov="ahmadi", cat="General Contracting", cat_ids=cat_ids, days=20)
    draft_offer(P1, pid, "6800", "Central chiller replacement, 2 year parts warranty")
    q1 = P3.j("POST", f"/projects/{pid}/clarifications", "ask question", json={"question": "Is the existing ducting to be reused?"})["id"]
    O1.must(O1.post(f"/projects/{pid}/clarifications/{q1}/answer", json={"answer": "Yes, reuse the main trunk; branches are to be replaced."}), "answer question")
    P1.j("POST", f"/projects/{pid}/clarifications", "ask second question", json={"question": "Can work be done outside prayer times only?"})
    am = O1.must(O1.patch(f"/projects/{pid}", json={"description": "Replace the central AC system of the prayer hall AND the ablution area. Branch ducting is to be replaced; main trunk reused. "
                                                                       "Work only outside prayer times.", "reason": "Scope clarified after provider questions"}), "material amendment")
    say("T08 open: 1 answered question, 1 UNANSWERED question, then a MATERIAL amendment (P1's offer now needs confirming)")

    T["T09"] = pid = open_tender(O2, "T09", "Compound Landscaping - Mishref (paused)", gov="mubarak_al_kabeer", cat="Landscaping", cat_ids=cat_ids, days=15)
    O2.must(O2.post(f"/owner/projects/{pid}/pause", json={"reason": "Waiting for the municipality's planting permit."}), "pause T09")
    say("T09 open but PAUSED by owner (resume it to test)")

    head("STAGE 6 - owner evaluates and decides")
    T["T10"] = pid = open_tender(O1, "T10", "Commercial Building Facade - Sharq (under evaluation)", gov="capital", cat="General Contracting", cat_ids=cat_ids, days=30)
    a = draft_offer(P1, pid, "48500", "Aluminium composite panels, scaffolding included", days=70)
    b = draft_offer(P3, pid, "45000", "Aluminium panels, tenant to provide scaffolding", days=60)
    O1.must(O1.post(f"/owner/projects/{pid}/close"), "close T10")
    O1.must(O1.post(f"/owner/projects/{pid}/start-evaluation"), "start evaluation T10")
    O1.must(O1.post(f"/owner/projects/{pid}/notes", json={"body": "P3 cheaper but excludes scaffolding - confirm total with them.", "offer_id": b}), "private note")
    O1.must(O1.put(f"/owner/projects/{pid}/offers/{a}/shortlist"), "shortlist P1 offer")
    c1 = O1.j("POST", f"/owner/projects/{pid}/offers/{b}/clarifications", "ask P3 a clarification", json={"question": "What is the all-in price including scaffolding?"})["id"]
    P3.must(P3.post(f"/projects/{pid}/offers/mine/clarifications/{c1}/answer", json={"answer": "Add 3,200 KWD for scaffolding hire."}), "P3 answers")
    O1.must(O1.post(f"/owner/projects/{pid}/offers/{a}/clarifications", json={"question": "Can the programme be shortened to 60 days?"}), "ask P1 a clarification (left unanswered)")
    say("T10 under_evaluation: 2 offers, private note, P1 shortlisted, 1 offer-clarification answered (P3), 1 unanswered (P1) - award it yourself")

    T["T14"] = pid = open_tender(O1, "T14", "Playground Surfacing - Mishref (no award)", gov="mubarak_al_kabeer", cat="Landscaping", cat_ids=cat_ids, days=30)
    draft_offer(P3, pid, "9500", "Rubber tile surfacing")
    O1.must(O1.post(f"/owner/projects/{pid}/close"), "close T14")
    O1.must(O1.post(f"/owner/projects/{pid}/no-award", json={"reason": "no_suitable_offer", "note": "Over budget."}), "no-award T14")
    say("T14 ended with NO AWARD (offer kept, status closed)")

    T["T15"] = pid = open_tender(O2, "T15", "Parking Shade Structure - Jahra (cancelled)", gov="jahra", cat="Civil Works", cat_ids=cat_ids, days=30)
    draft_offer(P3, pid, "13200", "Tensile shade structure")
    O2.must(O2.post(f"/owner/projects/{pid}/cancel", json={"reason": "postponed", "note": "Budget re-approval pending."}), "cancel T15")
    T["T03"] = t03 = O2.j("POST", f"/owner/projects/{pid}/restart", "restart T15 as a new draft")["id"]
    v03 = O2.j("GET", f"/projects/{t03}", "read restarted draft")["version"]
    O2.must(O2.patch(f"/projects/{t03}", json={"title": "[T03] Parking Shade Structure - Jahra (draft restarted from T15)"}, headers={"If-Match": str(v03)}), "rename T03")
    say("T15 CANCELLED (offer kept). T03 = the new DRAFT created from it with 'Start a new draft from this'")

    head("STAGE 7 - award, agreement, execution, completion")
    T["T11"] = pid = open_tender(O2, "T11", "Diwaniya Renovation - Andalous (awarded, agreement preparing)", gov="farwaniya", cat="General Contracting", cat_ids=cat_ids, days=30)
    w = draft_offer(P3, pid, "12000", "Full diwaniya renovation incl. seating and lighting")
    draft_offer(P1, pid, "13500", "Premium finishes, custom seating")
    close_and_award(O2, pid, w, "T11")
    milestone(O2, pid, "Demolition and preparation")
    say("T11 AWARDED to P3 (individual). Agreement status 'preparing', one milestone drafted. P1's offer rejected")

    T["T12"] = pid = open_tender(O1, "T12", "Office Fit-Out - Sharq (agreement in force, work under way)", gov="capital", cat="Finishing & Interior Fit-Out", cat_ids=cat_ids, days=30)
    w = draft_offer(S2, pid, "26000", "Fit-out of 600 sqm office, phased handover", days=75)
    draft_offer(P3, pid, "27500", "Fit-out of 600 sqm office")
    close_and_award(O1, pid, w, "T12")
    m1, m2, m3 = (milestone(O1, pid, t) for t in ("Partitions and ceilings", "Electrical first fix", "Flooring"))
    put_in_force(O1, P1, pid)
    S1.must(S1.post(f"/projects/{pid}/agreement/start-work", json={"note": "Team mobilised."}, headers=ver(S1, pid)), "start work")
    S1.must(S1.post(f"/projects/{pid}/agreement/progress", json={"action": "update", "note": "Partitions 60% complete."}, headers=ver(S1, pid)), "progress update")
    # m1 delivered + accepted, m2 delivered (waiting for owner), m3 returned for correction
    for mid in (m1, m2, m3):
        S1.must(S1.post(f"/projects/{pid}/agreement/milestones/{mid}/deliver", json={"note": "Ready for inspection."}, headers=mver(S1, pid, mid)), "deliver milestone")
    O1.must(O1.post(f"/projects/{pid}/agreement/milestones/{m1}/accept", json={}, headers=mver(O1, pid, m1)), "accept milestone")
    O1.must(O1.post(f"/projects/{pid}/agreement/milestones/{m3}/return", json={"note": "Uneven finish in room 2."}, headers=mver(O1, pid, m3)), "return milestone")
    P1.must(P1.post(f"/projects/{pid}/agreement/variations", json={"description": "Extra glass partition in meeting room.", "value_change": "1800", "add_deliverable": "Glass partition"},
                    headers=ver(P1, pid)), "propose variation")
    say("T12 AWARDED to P1 (offer made by staff diyar.staff2), agreement ACTIVE, work started by staff diyar.staff1; milestones: 1 accepted, 1 delivered, 1 returned; 1 variation PROPOSED (owner must decide)")

    T["T13"] = pid = open_tender(O2, "T13", "Roof Waterproofing - Salmiya (completed + reviews)", gov="hawalli", cat="General Contracting", cat_ids=cat_ids, days=30)
    w = draft_offer(P1, pid, "8400", "Bituminous membrane, 10 year guarantee")
    close_and_award(O2, pid, w, "T13")
    put_in_force(O2, P1, pid)
    P1.must(P1.post(f"/projects/{pid}/agreement/start-work", json={}, headers=ver(P1, pid)), "start work T13")
    P1.must(P1.post(f"/projects/{pid}/agreement/completion/submit", json={"note": "All roof areas done."}, headers=ver(P1, pid)), "submit completion")
    O2.must(O2.post(f"/projects/{pid}/agreement/completion/accept", json={}, headers=ver(O2, pid)), "accept completion")
    O2.must(O2.post("/owner/reviews", json={"project_id": pid, "rating": 2, "comment": "Finished late and left debris on site."}), "owner reviews provider")
    P1.must(P1.post("/service-provider/reviews", json={"project_id": pid, "rating": 5, "comment": "Clear brief and prompt acceptance."}), "provider reviews owner")
    P1.must(P1.post(f"/service-provider/projects/{pid}/review/received/response", json={"response": "The delay was caused by the site being unavailable for 5 days."}), "provider responds to review")
    P1.must(P1.post(f"/service-provider/projects/{pid}/review-reports", json={"target": "review", "reason": "other", "note": "Disputed facts - requesting admin look."}), "provider reports the review")
    say("T13 COMPLETED. Owner gave P1 a 2-star review; P1 responded and REPORTED it (sits in admin review-reports queue); P1 gave owner 5 stars")

    T["T16"] = pid = open_tender(O1, "T16", "Boundary Wall Repair - Jahra (agreement terminated)", gov="jahra", cat="Civil Works", cat_ids=cat_ids, days=30)
    w = draft_offer(P3, pid, "5200", "Repair and repaint 80 m of wall")
    close_and_award(O1, pid, w, "T16")
    put_in_force(O1, P3, pid)
    P3.must(P3.post(f"/projects/{pid}/agreement/start-work", json={}, headers=ver(P3, pid)), "start work T16")
    O1.must(O1.post(f"/projects/{pid}/agreement/terminate", json={"reason": "Provider did not attend site for two weeks."}, headers=ver(O1, pid)), "terminate agreement")
    say("T16 awarded to P3, agreement TERMINATED by owner")

    head("STAGE 9 - admin moderation")
    T["T17"] = pid = open_tender(O2, "T17", "Garden Pergola - Mishref (admin-suspended)", gov="mubarak_al_kabeer", cat="Landscaping", cat_ids=cat_ids, days=15)
    admin.must(admin.post(f"/admin/projects/{pid}/suspend", json={"suspended": True, "reason": "Stage test data: suspended for moderation testing."}), "admin-suspend T17")
    say("T17 open but SUSPENDED by admin (hidden from provider feed)")
    return T


# ----------------------------------------------------------------------------
# Self-check: confirm the data really sits where the guide says it does
# ----------------------------------------------------------------------------
EXPECTED_STATUS = {
    "T01": "draft", "T02": "draft", "T03": "draft", "T04": "open", "T05": "open", "T06": "open", "T07": "open", "T08": "open", "T09": "open",
    "T10": "under_evaluation", "T11": "awarded", "T12": "awarded", "T13": "awarded", "T14": "no_award", "T15": "canceled", "T16": "awarded", "T17": "open",
}


def self_check(admin: Client, cast: dict, tenders: dict) -> list[str]:
    from app.models.offer import Offer
    from app.models.organization import OrganizationMembership
    from app.models.project import Project
    from app.models.user import User
    problems: list[str] = []
    with db_session() as db:
        n = db.query(User).count()
        if n != 11:
            problems.append(f"expected 11 users, found {n}")
        for code, want in EXPECTED_STATUS.items():
            got = db.get(Project, tenders[code]).status.value
            if got != want:
                problems.append(f"{code}: expected status {want}, found {got}")
        for code, n_offers in (("T06", 2), ("T07", 2), ("T08", 1), ("T10", 2), ("T11", 2), ("T12", 2), ("T13", 1), ("T14", 1), ("T15", 1), ("T16", 1)):
            got = db.query(Offer).filter(Offer.project_id == tenders[code]).count()
            if got != n_offers:
                problems.append(f"{code}: expected {n_offers} offers, found {got}")
        if not db.get(Project, tenders["T17"]).is_suspended:
            problems.append("T17 is not admin-suspended")
        members = {k: db.query(OrganizationMembership).filter(OrganizationMembership.user_id == cast["providers"][k].user_id).count() for k in cast["providers"]}
        if members != {"P1": 1, "P2": 1, "P3": 0, "P4": 1}:
            problems.append(f"unexpected provider memberships {members}")
    ag = lambda c, code: agreement(c, tenders[code])["status"]
    for code, owner, want in (("T11", "O2", "preparing"), ("T12", "O1", "active"), ("T13", "O2", "completed"), ("T16", "O1", "terminated")):
        got = ag(cast["owners"][owner], code)
        if got != want:
            problems.append(f"{code}: agreement expected {want}, found {got}")
    if not [r for r in admin.j("GET", "/admin/review-reports", "list review reports") if r.get("status") == "open"]:
        problems.append("no open review report for the moderation queue")
    return problems


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api-url", default="http://localhost:8000", help="where the backend API is reachable")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()

    from app.config import get_settings
    from sqlalchemy.engine import make_url
    url = make_url(get_settings().database_url)
    shown = f"{url.drivername}://{url.username or ''}@{url.host or ''}/{url.database}" if url.host else str(url).split("///")[0] + "///" + (url.database or "")
    print(f"\nTarget API : {args.api_url}\nTarget DB  : {shown}\n")
    print("This ONE-TIME script will create 11 accounts and ~17 tenders (admin, 2 owners, 4 providers, 4 staff).")
    if not args.yes and input("Run it against this database? Type 'yes' to continue: ").strip().lower() != "yes":
        sys.exit("Aborted.")

    try:
        requests.get(f"{args.api_url.rstrip('/')}/health", timeout=10).raise_for_status()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"API not reachable at {args.api_url}: {e}")

    taken = [e for e in [ADMIN["email"]] + [o["email"] for o in OWNERS.values()] + [p["email"] for p in PROVIDERS.values()] if db_user_exists(e)]
    if taken:
        sys.exit("Already seeded (these accounts exist): " + ", ".join(taken) + "\nThis script is deliberately one-time. Restore a clean database/backup to run it again.")

    started = time.time()
    head("Admin")
    db_create_admin(ADMIN["email"], ADMIN["name"])
    admin = Client(args.api_url, ADMIN["email"])
    admin.login(ADMIN["email"])
    say(f"{ADMIN['email']}")

    head("Platform setup: service categories and verification documents (reusing whatever already exists)")
    have_cats = {c["name"].strip().lower(): c["id"] for c in admin.j("GET", "/admin/categories", "list categories")}
    cat_ids, made = {}, []
    for name in CATEGORIES:
        if name.lower() in have_cats:
            cat_ids[name] = have_cats[name.lower()]
        else:
            cat_ids[name] = admin.j("POST", "/admin/categories", f"add category {name}", json={"name": name})["id"]
            made.append(name)
    say(f"categories: {len(CATEGORIES)} needed, {len(made)} created ({', '.join(made) or 'all already existed'})")

    existing = [r for r in admin.j("GET", "/admin/requirements", "list requirements") if r.get("is_active", True)]
    have = lambda role: any(r.get("applies_to") == role for r in existing)
    wanted = [
        ("Owner Civil ID", "Civil ID of the account holder.", "owner", "individual", True),
        ("Owner Company License", "Ministry of Commerce license of the company.", "owner", "organization", True),
        ("Owner Authorized Signatory Letter", "Letter authorising the representative to act for the company.", "owner", "organization", True),
        ("Freelancer Civil ID", "Civil ID of the freelancer.", "service_provider", "individual", True),
        ("Freelancer Trade Permit", "Permit to trade as an individual contractor.", "service_provider", "individual", True),
        ("Contractor Commercial License", "Kuwait commercial license for the contracting company.", "service_provider", "organization", True),
        ("Contractor Chamber of Commerce Certificate", "Kuwait Chamber of Commerce membership certificate.", "service_provider", "organization", True),
    ]
    created = 0
    for name, desc, applies, stake, required in wanted:
        if have(applies):  # the deployment already defines this side's checklist: don't pile ours on top of it
            continue
        admin.j("POST", "/admin/requirements", f"add requirement {name}", json={"name": name, "description": desc, "is_required": required, "applies_to": applies, "applies_to_stakeholder": stake})
        created += 1
    qual = next((r for r in existing if "iso 9001" in r["name"].lower()), None)
    if qual is None:
        qual = admin.j("POST", "/admin/requirements", "add ISO 9001 qualification", json={
            "name": "ISO 9001 Quality Certificate", "description": "Optional quality-management certification (used as a tender qualification).",
            "is_required": False, "applies_to": "service_provider", "applies_to_stakeholder": "organization"})
        created += 1
    qual_id = qual["id"]
    say(f"document requirements: {created} created, the rest reused ({len(existing)} already defined)")

    cast = build_cast(args.api_url, admin, cat_ids)
    tenders = build_tenders(admin, cast, cat_ids, qual_id)

    head("Self-check")
    problems = self_check(admin, cast, tenders)
    if problems:
        say("PROBLEMS: " + "; ".join(problems))
    else:
        say("all 11 users, 17 tenders, offers, agreements and moderation items are where the guide says they are")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "api_url": args.api_url, "password_for_every_account": PASSWORD,
        "accounts": {"admin": ADMIN["email"], "owners": {k: v["email"] for k, v in OWNERS.items()},
                     "providers": {k: v["email"] for k, v in PROVIDERS.items()},
                     "staff": {k: [em(s[0]) for s in v["staff"]] for k, v in PROVIDERS.items()}},
        "pending_invitations": cast["invitations"], "tenders": tenders,
    }
    (HERE / "last_run_manifest.json").write_text(json.dumps(manifest, indent=2))

    head("Done")
    n_users = 1 + len(OWNERS) + len(PROVIDERS) + sum(len(p["staff"]) for p in PROVIDERS.values())
    say(f"{n_users} users, {len(tenders)} tenders in {time.time() - started:.0f}s. Password for EVERY account: {PASSWORD}")
    say("Guide: stage-test-data/TEST-DATA-GUIDE.md   Ids/links: stage-test-data/last_run_manifest.json")
    for email, inv in cast["invitations"].items():
        say(f"Pending invitation for {email}: {inv['link']}")


if __name__ == "__main__":
    main()

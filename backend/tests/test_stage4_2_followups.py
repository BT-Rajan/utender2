"""Stage 4.2 follow-ups: search that tolerates Arabic letter variants and word
endings and puts the best text matches first; "my types of work" that also
recognises free-text types of work; and eligibility applied in the feed's
database query -- deciding exactly as the rules providers are held to."""
import itertools
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models.category import ServiceCategory
from app.models.document import DocumentRequirement, ServiceProviderDocument
from app.models.enums import DocumentStatus, StakeholderType, UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.services.eligibility import feed_condition, ineligibility_reasons


def _when(days: float) -> str:
    return (datetime.utcnow() + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _verified(db, role: str, email: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/signup", json={"email": email, "password": "password123", "full_name": "N", "role": role})
    c.put("/account/stakeholder", json={"type": "individual"})
    model = OwnerProfile if role == "owner" else ServiceProviderProfile
    profile = db.get(model, r.json()["id"])
    profile.verification_status = VerificationStatus.approved
    if role == "service_provider":
        profile.company_name = email.split("@")[0]
        profile.payment_override_active = True
    db.commit()
    return c


def _publish(owner, title, days=10, **data):
    r = owner.post("/projects", data={"title": title, "address": "Plot 1", "bid_deadline": _when(days), "status": "open", **data})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _titles(client, **params):
    r = client.get("/service-provider/feed", params=params)
    assert r.status_code == 200, r.text
    return [p["title"] for p in r.json()["items"]]


def test_arabic_variants_word_endings_and_relevance(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sami@example.com")
    _publish(owner, "صيانة الكهربائية لمبنى", governorate="hawalli", description="تمديدات وإنارة لثلاثة أدوار.")
    _publish(owner, "دهان شقة", governorate="capital", description="دهانات داخلية وإصلاح الكهرباء البسيط.", days=5)
    _publish(owner, "Shop lighting", trade="Lighting", governorate="ahmadi", description="Install LED panels.")
    _publish(owner, "Office repaint", governorate="capital", description="Interior painting, two floors.", days=3)

    assert _titles(sp, search="كهرباء") == ["دهان شقة", "صيانة الكهربائية لمبنى"]  # hamza, ة/ه, ال
    assert sorted(_titles(sp, search="الإنارة")) == sorted(["صيانة الكهربائية لمبنى", "Shop lighting"])  # same deadline: either order  # إ/ا, the article -- and "lighting" is the same work
    assert _titles(sp, search="حولي") == ["صيانة الكهربائية لمبنى"]  # governorate by its Arabic name
    assert _titles(sp, search="Kuwait City") == ["Office repaint", "دهان شقة"]
    assert _titles(sp, search="paints") == ["Office repaint", "دهان شقة"]  # "paints" ~ "painting", and its Arabic synonym
    assert sorted(_titles(sp, search="LIGHTS")) == sorted(["صيانة الكهربائية لمبنى", "Shop lighting"])  # case; and "إنارة" is lighting
    # Relevance: found in the title first, then by deadline.
    assert _titles(sp, search="كهرباء", sort="relevance") == ["صيانة الكهربائية لمبنى", "دهان شقة"]
    assert _titles(sp, sort="relevance") == _titles(sp)  # no search: the usual order


def test_my_types_of_work_recognises_free_text(db):
    electrical = ServiceCategory(name="Electrical", is_active=True)
    db.add(electrical)
    db.commit()
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sami@example.com")
    _publish(owner, "Listed", category_id=electrical.id)
    _publish(owner, "Free text", trade="Electrical maintenance")
    _publish(owner, "Other", trade="Plumbing")
    sp.put("/service-provider/services", json={"categories": [electrical.id]})
    assert sorted(_titles(sp, my_services=True)) == ["Free text", "Listed"]


def test_a_category_rename_follows_into_search(db):
    admin_cat = ServiceCategory(name="Electrical", is_active=True)
    db.add(admin_cat)
    db.commit()
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sami@example.com")
    _publish(owner, "Villa job", category_id=admin_cat.id)
    from app.services.categories import rename_category

    rename_category(db, admin_cat, "Electromechanical")
    db.commit()
    assert _titles(sp, search="electromechanical") == ["Villa job"]


def test_the_feed_query_decides_eligibility_as_the_rules_do(db):
    """Every combination of rule and provider situation: the database
    condition and ineligibility_reasons() must agree, one by one."""
    from sqlalchemy import select

    lic_a = DocumentRequirement(name="Licence A", is_required=False, applies_to=UserRole.service_provider)
    lic_b = DocumentRequirement(name="Licence B", is_required=False, applies_to=UserRole.service_provider)
    electrical, plumbing = ServiceCategory(name="Electrical", is_active=True), ServiceCategory(name="Plumbing", is_active=True)
    db.add_all([lic_a, lic_b, electrical, plumbing])
    db.commit()
    owner = _verified(db, "owner", "owner@example.com")
    owner_id = owner.get("/auth/me").json()["id"]

    # Requirements: every mix of rule.
    projects = []
    for org_only, quals, match_cat, match_gov, cat, gov in itertools.product(
        (False, True), ((), (lic_a.id,), (lic_a.id, lic_b.id)), (False, True), (False, True), (electrical.id, None), ("hawalli", None),
    ):
        if (match_cat and not cat) or (match_gov and not gov):
            continue  # refused when set (validate_rules); covered below as "subject cleared"
        rules = {"provider_type": "organization" if org_only else "any", "qualifications": list(quals), "match_category": match_cat, "match_governorate": match_gov}
        p = Project(owner_id=owner_id, title="R", address="x", bid_deadline=datetime.utcnow() + timedelta(days=5), category_id=cat, governorate=gov, provider_eligibility=rules)
        db.add(p)
        projects.append(p)
    # A rule whose subject was later cleared restricts nothing.
    cleared = Project(owner_id=owner_id, title="R", address="x", bid_deadline=datetime.utcnow() + timedelta(days=5), provider_eligibility={"match_category": True, "match_governorate": True})
    db.add(cleared)
    projects.append(cleared)
    db.commit()

    # Providers: individual/organization x documents held (none, A, A+B, A expired, B rejected) x declared services.
    situations = []
    for i, (org, docs, cats, govs) in enumerate(itertools.product(
        (False, True),
        ((), ((lic_a.id, "approved", None),), ((lic_a.id, "approved", None), (lic_b.id, "approved", date.today())), ((lic_a.id, "approved", date.today() - timedelta(days=1)),), ((lic_b.id, "rejected", None),)),
        ([], [electrical.id], [plumbing.id]),
        ([], ["hawalli"], ["jahra"]),
    )):
        c = TestClient(app)
        uid = c.post("/auth/signup", json={"email": f"p{i}@example.com", "password": "password123", "full_name": "N", "role": "service_provider"}).json()["id"]
        prof = db.get(ServiceProviderProfile, uid)
        prof.stakeholder_type = StakeholderType.organization if org else StakeholderType.individual
        prof.service_categories, prof.service_governorates = cats, govs
        for req, status, expires in docs:
            d = db.query(ServiceProviderDocument).filter_by(service_provider_id=uid, requirement_id=req).first() or ServiceProviderDocument(service_provider_id=uid, requirement_id=req)
            d.status, d.expires_on = DocumentStatus(status), expires
            db.add(d)
        situations.append(prof)
    db.commit()

    checked = 0
    for prof in situations:
        in_sql = set(db.execute(select(Project.id).where(Project.id.in_([p.id for p in projects]), feed_condition(db, prof))).scalars())
        for p in projects:
            assert (p.id in in_sql) == (not ineligibility_reasons(db, p, prof)), (p.provider_eligibility, p.category_id, p.governorate, prof.stakeholder_type, prof.service_categories, prof.service_governorates)
            checked += 1
    assert checked > 2000


def test_synonyms_typos_and_short_words(db):
    owner = _verified(db, "owner", "owner@example.com")
    sp = _verified(db, "service_provider", "sami@example.com")
    _publish(owner, "Electrical rewiring", description="Replace the DB board.", days=3)
    _publish(owner, "تركيب مكيفات", description="ثلاثة مكيفات سبليت.", days=4)
    _publish(owner, "Bathroom plumbing", description="New pipes and fittings.", days=5)
    _publish(owner, "Facade paint", description="Paint the facade; scaffolding by the contractor.", days=6)
    # Synonyms across languages, both ways.
    assert _titles(sp, search="كهرباء") == ["Electrical rewiring"]
    assert _titles(sp, search="سباكة") == ["Bathroom plumbing"]
    assert _titles(sp, search="AC") == ["تركيب مكيفات"]
    # Typos, against what open opportunities actually say.
    assert _titles(sp, search="elecrtical") == ["Electrical rewiring"]
    assert _titles(sp, search="plumbng") == ["Bathroom plumbing"]
    # A short word must start a word: "ac" isn't found inside "facade" or "replace".
    assert "Facade paint" not in _titles(sp, search="ac") and "Electrical rewiring" not in _titles(sp, search="ac")


def test_the_eligibility_rules_and_the_feed_condition_change_together():
    """A guard: the feed applies eligibility in SQL (eligibility.feed_condition
    over the derived Project.elig_* columns kept by models.project.sync_derived),
    mirroring ineligibility_reasons(). A new or renamed rule must be added in
    all three places -- this fails first, saying so, before anything drifts."""
    from app.schemas.project import ProviderEligibilityIn

    assert set(ProviderEligibilityIn.model_fields) == {"provider_type", "qualifications", "match_category", "match_governorate"}, (
        "The eligibility rules changed: update ineligibility_reasons(), feed_condition() and sync_derived() "
        "(plus a migration for any new elig_* column) together, then extend the parity test above and this list."
    )

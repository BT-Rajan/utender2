"""Stage 3.12: the pre-publication quality gate.

"If this requirement were published now, could a competent provider
understand it, decide whether to respond, and prepare a meaningful offer?"

check() looks at what Stage 3 already records and returns:

  errors    block publication: essential information missing, invalid or
            contradictory.
  warnings  may weaken the requirement; the owner decides.

Each issue names the section of the draft to correct (details, dates, rules,
items, response, eligibility, documents) and carries a code the interface
translates, plus an English message used in API errors.

Not every requirement is the same: a simple service (AC servicing) needs a
clear scope, a location and a deadline; drawings, quantities and dates are
only expected of a *detailed* requirement -- one priced per item or listing
several items -- and even then only warned about, unless the owner has said
providers need the documents to price (documents_required), which makes a
missing document an error. Nothing here scores or guesses at the wording:
every rule is a plain, explainable check.

The gate is authoritative server-side (assert_publishable, called on every
path that publishes); the draft page shows the same list.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.category import ServiceCategory
from app.models.enums import PricingBasis
from app.models.project import Project, ProjectDrawing

MIN_TITLE = 5
MIN_SCOPE = 30  # below this there is no meaningful description of the work
BRIEF_SCOPE = 120
DETAILED_ITEMS = 5
SHORT_WINDOW = timedelta(days=3)

@dataclass
class Issue:
    code: str
    section: str
    message: str
    params: dict = field(default_factory=dict)


@dataclass
class QualityReport:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ready": self.ready, "errors": [asdict(i) for i in self.errors], "warnings": [asdict(i) for i in self.warnings]}


def check(db: Session, project: Project) -> QualityReport:
    r = QualityReport()
    err = lambda code, section, message, **params: r.errors.append(Issue(code, section, message, params))  # noqa: E731
    warn = lambda code, section, message, **params: r.warnings.append(Issue(code, section, message, params))  # noqa: E731
    now = datetime.utcnow()
    items = list(project.items or [])
    scope = (project.description or "").strip()
    documents = (
        db.query(ProjectDrawing).filter(ProjectDrawing.project_id == project.id, ProjectDrawing.is_current.is_(True)).count()
        if project.id
        else 0
    )
    detailed = project.pricing_basis == PricingBasis.per_item or len(items) >= DETAILED_ITEMS

    # --- what is being requested ---
    if len((project.title or "").strip()) < MIN_TITLE:
        err("title_too_short", "details", "Give the requirement a title that says what the work is (at least 5 characters).")
    if len(scope) < MIN_SCOPE and not items:
        err("scope_missing", "details", "Describe the work: what needs doing, where on the site and to what standard. A provider can't price a requirement without it.")
    elif len(scope) < BRIEF_SCOPE:
        warn("scope_brief", "details", "The scope is very brief. Providers price more accurately when they know exactly what's included and what isn't.")
    if not project.trade:
        warn("type_missing", "details", "Choose the type of work, so the right providers find it.")
    elif project.category_id is None and db.query(ServiceCategory.id).filter(ServiceCategory.is_active.is_(True)).first():
        warn("type_unlisted", "details", "The type of work isn't one of the platform's categories, so providers filtering by category won't find it.")

    # --- where ---
    if not (project.address or "").strip():
        err("address_missing", "details", "Give the site address or a description of where the site is.")
    if not project.governorate:
        err("governorate_missing", "details", "Choose the governorate, so providers can judge travel and whether they cover the area.")
    elif not project.area:
        warn("area_missing", "details", "Add the area (e.g. Salwa), so providers can judge the location without the exact address.")

    # --- when ---
    if project.bid_deadline is None or project.bid_deadline <= now:
        err("deadline_passed", "dates", "Set an offer deadline in the future.")
    else:
        if project.bid_deadline - now < SHORT_WINDOW:
            warn("deadline_soon", "dates", "Offers close in under 3 days. Providers may not have time to visit the site and price properly.")
        from app.routers.projects import _check_execution_timing  # the same rule as when the dates are saved

        try:
            _check_execution_timing(
                project.bid_deadline, project.expected_start_date, project.expected_completion_date, project.expected_duration_days
            )
        except HTTPException as exc:
            err("timing_contradiction", "dates", str(exc.detail))
    if detailed and not (project.expected_start_date or project.expected_completion_date or project.expected_duration_days):
        warn("timing_missing", "dates", "Say roughly when the work should happen (a start date or a duration), so providers can check their availability.")
    if project.questions_allowed and project.questions_deadline and project.questions_deadline <= now:
        err("questions_deadline_passed", "rules", "The question deadline has passed: move it later, or remove it to take questions until offers close.")

    # --- what to price ---
    if project.pricing_basis == PricingBasis.per_item and not items:
        err("per_item_without_items", "items", "The requirement is priced per item but lists no items. Add the items, or price it as one total.")
    for item in items:
        if item.quantity is not None and not (item.unit or "").strip():
            err("item_unit_missing", "items", f'Item {item.position} ("{item.description}") has a quantity but no unit.', position=item.position)
        elif project.pricing_basis == PricingBasis.per_item and item.quantity is None:
            warn(
                "item_quantity_missing",
                "items",
                f'Item {item.position} ("{item.description}") has no quantity, so providers will price it as a lump sum.',
                position=item.position,
            )

    # --- who may respond (Stage 3.9 rules whose subject has since changed) ---
    rules = project.provider_eligibility or {}
    if rules.get("match_category") and not project.category_id:
        err("eligibility_category_missing", "eligibility", "Who can respond depends on the type of work, but none from the platform's list is chosen.")
    if rules.get("match_governorate") and not project.governorate:
        err("eligibility_governorate_missing", "eligibility", "Who can respond depends on the governorate, but none is chosen.")
    if rules.get("qualifications"):
        from app.services.eligibility import qualification_options

        active = {q.id for q in qualification_options(db)}
        if any(q not in active for q in rules["qualifications"]):
            err("qualification_retired", "eligibility", "A required qualification is no longer on the platform's list. Choose again under Who can respond.")

    # --- supporting documents ---
    if not documents and project.documents_required:
        err(
            "documents_required_missing",
            "documents",
            "The requirement depends on its documents, but none are uploaded. Upload them, or untick that providers need them to price.",
        )
    elif not documents and detailed:
        warn("documents_missing", "documents", "No drawings, BOQ or photos are attached. For detailed work, providers usually need them to price accurately.")
    return r


def assert_publishable(db: Session, project: Project) -> None:
    """Every path that publishes calls this: the server, not the page, decides."""
    report = check(db, project)
    if report.errors:
        raise HTTPException(
            status_code=400,
            detail="This requirement isn't ready to publish. " + " ".join(i.message for i in report.errors),
        )

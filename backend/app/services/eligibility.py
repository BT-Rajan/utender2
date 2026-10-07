"""Stage 3.9: requirement-specific provider eligibility.

Kept separate from, and layered on top of, platform verification:

  account exists -> stakeholder established -> platform verification
  (ServiceProviderProfile.is_verified_active, the onboarding gate) ->
  eligibility for THIS requirement (here).

A requirement may narrow who can respond in these ways, all optional and
all built on what the platform already records:

  provider_type   "organization": only providers registered as an
                  organization (the Step 3 stakeholder type).
  match_category / match_governorate
                  the provider's declared services (ServiceProviderProfile.
                  service_categories / service_governorates) must include the
                  requirement's category / governorate.
  qualifications  ids of the platform's provider verification requirements
                  (the admin-managed DocumentRequirement list). The provider
                  must hold that document, approved by the platform and not
                  expired.

Nothing here names a specific licence, certificate or document. The same
function decides both what a provider is told and what the server enforces.
"""
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.document import DocumentRequirement, ServiceProviderDocument
from app.models.enums import DocumentStatus, StakeholderType, UserRole
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.services.team import team_ids
from app.schemas.project import EligibilityQualification, EligibilityReason, ProviderEligibilityIn, ProviderEligibilityOut


def rules_for(project: Project) -> ProviderEligibilityIn:
    return ProviderEligibilityIn(**(project.provider_eligibility or {}))


def qualification_options(db: Session) -> list[DocumentRequirement]:
    """What an owner can ask for: the platform's current provider verification
    requirements."""
    return (
        db.query(DocumentRequirement)
        .filter(DocumentRequirement.is_active.is_(True), DocumentRequirement.applies_to == UserRole.service_provider)
        .order_by(DocumentRequirement.name.asc())
        .all()
    )


def validate_rules(db: Session, rules: ProviderEligibilityIn, project: Project) -> dict:
    allowed = {r.id for r in qualification_options(db)}
    if any(q not in allowed for q in rules.qualifications):
        raise HTTPException(status_code=400, detail="Choose qualifications from the platform's list of provider documents.")
    if rules.match_category and not project.category_id:
        raise HTTPException(status_code=400, detail="Choose the type of work from the platform's list before restricting by it.")
    if rules.match_governorate and not project.governorate:
        raise HTTPException(status_code=400, detail="Set the governorate before restricting by it.")
    return rules.model_dump()


def rules_out(db: Session, project: Project) -> ProviderEligibilityOut:
    rules = rules_for(project)
    reqs = {r.id: r for r in db.query(DocumentRequirement).filter(DocumentRequirement.id.in_(rules.qualifications or [""]))}
    return ProviderEligibilityOut(
        provider_type=rules.provider_type,
        qualifications=[
            EligibilityQualification(id=q, name=reqs[q].name, description=reqs[q].description) for q in rules.qualifications if q in reqs
        ],
        match_category=rules.match_category,
        match_governorate=rules.match_governorate,
        category=project.trade if rules.match_category else None,
        governorate=project.governorate if rules.match_governorate else None,
    )


def ineligibility_reasons(db: Session, project: Project, profile: ServiceProviderProfile) -> list[EligibilityReason]:
    """Why this provider can't respond to this requirement; empty = eligible.
    Platform verification itself is checked separately, by the callers'
    existing gates. Each reason carries a code for the interface to translate
    and an English sentence for API errors."""
    rules = rules_for(project)
    reasons: list[EligibilityReason] = []
    if rules.provider_type == "organization" and profile.stakeholder_type != StakeholderType.organization:
        reasons.append(EligibilityReason(
            code="organization_only",
            fixable=False,
            message="This requirement is open to providers registered as an organization only; your account is registered as an individual.",
        ))
    if rules.qualifications:
        names = {r.id: r.name for r in db.query(DocumentRequirement).filter(DocumentRequirement.id.in_(rules.qualifications))}
        # An organization's qualification counts for every member, whoever
        # in it holds the approved document.
        team = team_ids(db, profile.user_id)
        held: dict[str, ServiceProviderDocument] = {}
        for d in db.query(ServiceProviderDocument).filter(
            ServiceProviderDocument.service_provider_id.in_(team),
            ServiceProviderDocument.requirement_id.in_(rules.qualifications),
            ServiceProviderDocument.status == DocumentStatus.approved,
        ):
            best = held.get(d.requirement_id)
            if best is None or (best.expires_on is not None and (d.expires_on is None or d.expires_on > best.expires_on)):
                held[d.requirement_id] = d
        today = date.today()
        for q in rules.qualifications:
            name = names.get(q, "a required qualification")
            doc = held.get(q)
            if not doc:
                reasons.append(EligibilityReason(
                    code="qualification_missing",
                    fixable=True,
                    name=name,
                    message=f'This requirement needs a platform-approved "{name}"; your verification doesn\'t include an approved one.',
                ))
            elif doc.expires_on is not None and doc.expires_on < today:
                reasons.append(EligibilityReason(
                    code="qualification_expired",
                    fixable=True,
                    name=name,
                    date=doc.expires_on.isoformat(),
                    message=f'This requirement needs a valid "{name}"; yours expired on {doc.expires_on.isoformat()}.',
                ))
    # A rule whose subject was later cleared from the requirement restricts nothing.
    team_profiles = (
        db.query(ServiceProviderProfile).filter(ServiceProviderProfile.user_id.in_(team_ids(db, profile.user_id))).all()
        if (rules.match_category or rules.match_governorate)
        else [profile]
    )
    offered = {c for p in team_profiles for c in (p.service_categories or [])}
    if rules.match_category and project.category_id and project.category_id not in offered:
        reasons.append(EligibilityReason(
            code="category_not_offered",
            fixable=True,
            name=project.trade,
            message=f'This requirement is for "{project.trade}"; your profile doesn\'t list it among your services.',
        ))
    # The governorates the organization's members serve; none declared = all of Kuwait.
    served = {g for p in team_profiles for g in (p.service_governorates or [])}
    if rules.match_governorate and project.governorate and served and project.governorate not in served:
        reasons.append(EligibilityReason(
            code="governorate_not_served",
            fixable=True,
            governorate=project.governorate,
            message=f"This requirement is in {project.governorate.replace('_', ' ').title()}, which isn't among the governorates your profile says you serve.",
        ))
    return reasons


def feed_condition(db: Session, profile: ServiceProviderProfile):
    """Stage 4.2 follow-up: ineligibility_reasons() as one SQL condition over
    the derived Project.elig_* columns, so the provider feed filters and pages
    in the database. It must decide exactly as ineligibility_reasons() does
    (tests/test_stage4_2_followups.py checks the two agree); that function
    stays the authority for everything a provider is told or refused.
    Changing the rules (schemas.project.ProviderEligibilityIn) means changing
    this, models.project.sync_derived and ineligibility_reasons() together;
    tests/test_stage4_2_followups.py fails until all three agree."""
    from sqlalchemy import and_, func, or_, true

    conditions = []
    if profile.stakeholder_type != StakeholderType.organization:
        conditions.append(Project.elig_org_only.is_(False))
    # Qualifications: every one the requirement lists must be held, approved
    # and in date, by someone in the provider's organization.
    today = date.today()
    held = sorted({
        d.requirement_id
        for d in db.query(ServiceProviderDocument).filter(
            ServiceProviderDocument.service_provider_id.in_(team_ids(db, profile.user_id)),
            ServiceProviderDocument.status == DocumentStatus.approved,
            or_(ServiceProviderDocument.expires_on.is_(None), ServiceProviderDocument.expires_on >= today),
        )
    })
    remaining = Project.elig_quals
    for requirement_id in held:  # strike each held one from ",a,b,"; all held leaves ","
        remaining = func.replace(remaining, f",{requirement_id},", ",")
    conditions.append(or_(Project.elig_quals.is_(None), remaining == ","))
    team_profiles = db.query(ServiceProviderProfile).filter(ServiceProviderProfile.user_id.in_(team_ids(db, profile.user_id))).all()
    offered = sorted({c for p in team_profiles for c in (p.service_categories or [])})
    conditions.append(or_(Project.elig_match_category.is_(False), Project.category_id.is_(None), Project.category_id.in_(offered)))
    served = sorted({g for p in team_profiles for g in (p.service_governorates or [])})
    if served:  # none declared = all of Kuwait
        conditions.append(or_(Project.elig_match_governorate.is_(False), Project.governorate.is_(None), Project.governorate.in_(served)))
    return and_(true(), *conditions)


def availability(project: Project) -> str:
    """Where the requirement stands for participation, from its authoritative
    state: open, paused (by its owner), ended (closed, past its deadline,
    or a final outcome), or unavailable (hidden by U-Tender)."""
    from datetime import datetime

    from app.models.enums import ProjectStatus

    if project.is_suspended:
        return "unavailable"
    if project.status == ProjectStatus.open and project.bid_deadline > datetime.utcnow():
        return "paused" if project.paused_at is not None else "open"
    return "ended"


def participation(db: Session, project: Project, profile: ServiceProviderProfile | None, reasons: list[EligibilityReason] | None = None):
    """Stage 4.5: can this provider take part in this requirement, and if not
    why -- lifecycle first (eligibility never reopens anything), then the
    provider's platform standing, then this requirement's conditions, then
    marketplace access. The offer endpoints enforce exactly these checks."""
    from app.models.enums import VerificationStatus
    from app.schemas.project import Participation

    state = availability(project)
    if state != "open":
        return Participation(status="unavailable", availability=state)
    if profile and profile.is_suspended:
        return Participation(status="action_required", action="account_suspended", availability=state)
    if not profile or profile.verification_status != VerificationStatus.approved:
        return Participation(status="action_required", action="verification", availability=state)
    if reasons is None:
        reasons = ineligibility_reasons(db, project, profile)
    if reasons:
        return Participation(status="not_eligible", availability=state)
    if not profile.is_verified_active:
        return Participation(status="action_required", action="activate_access", availability=state)
    return Participation(status="can_participate", availability=state)


def assert_eligible(db: Session, project: Project, profile: ServiceProviderProfile) -> None:
    reasons = ineligibility_reasons(db, project, profile)
    if reasons:
        raise HTTPException(
            status_code=403, detail="You aren't eligible to respond to this requirement. " + " ".join(r.message for r in reasons)
        )


def audience(db: Session, project: Project) -> dict:
    """Stage 3.13: who this requirement would reach, for the owner's preview --
    counts only, never who. Among providers who can currently take part
    (verified, active access), how many meet its rules, and how many each
    rule leaves out. Uses the same check providers are held to."""
    profiles = (
        db.query(ServiceProviderProfile)
        .filter(ServiceProviderProfile.verification_status == "approved", ServiceProviderProfile.is_suspended.is_(False))
        .all()
    )
    active = [p for p in profiles if p.is_verified_active]
    excluded: dict[str, int] = {}
    eligible = 0
    for profile in active:
        reasons = ineligibility_reasons(db, project, profile)
        if not reasons:
            eligible += 1
        for code in {r.code for r in reasons}:
            excluded[code] = excluded.get(code, 0) + 1
    return {"active_providers": len(active), "eligible": eligible, "excluded_by": excluded}


def matching_providers(db: Session, project: Project) -> list[ServiceProviderProfile]:
    """Stage 3.14: who to tell about a newly published requirement -- not every
    provider, only those it is genuinely for: able to take part now (verified,
    active access), meeting its "who can respond" rules, offering its type of
    work, and serving its governorate (or not limited to any). A requirement
    without a type of work from the platform's list notifies nobody, since
    there is no way to tell who it is relevant to; providers still find it in
    the list of opportunities."""
    if not project.category_id:
        return []
    out = []
    for profile in db.query(ServiceProviderProfile).filter(ServiceProviderProfile.verification_status == "approved").all():
        if not profile.is_verified_active or ineligibility_reasons(db, project, profile):
            continue
        team = db.query(ServiceProviderProfile).filter(ServiceProviderProfile.user_id.in_(team_ids(db, profile.user_id))).all()
        if project.category_id not in {c for p in team for c in (p.service_categories or [])}:
            continue
        served = {g for p in team for g in (p.service_governorates or [])}
        if served and project.governorate and project.governorate not in served:
            continue
        out.append(profile)
    return out

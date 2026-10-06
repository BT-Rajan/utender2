"""Stage 3.9: requirement-specific provider eligibility.

Kept separate from, and layered on top of, platform verification:

  account exists -> stakeholder established -> platform verification
  (ServiceProviderProfile.is_verified_active, the onboarding gate) ->
  eligibility for THIS requirement (here).

A requirement may narrow who can respond in two ways, both optional and
both built on what the platform already records:

  provider_type   "organization": only providers registered as an
                  organization (the Step 3 stakeholder type).
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
from app.schemas.project import EligibilityQualification, ProviderEligibilityIn, ProviderEligibilityOut


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


def validate_rules(db: Session, rules: ProviderEligibilityIn) -> dict:
    allowed = {r.id for r in qualification_options(db)}
    unknown = [q for q in rules.qualifications if q not in allowed]
    if unknown:
        raise HTTPException(status_code=400, detail="Choose qualifications from the platform's list of provider documents.")
    return rules.model_dump()


def rules_out(db: Session, project: Project) -> ProviderEligibilityOut:
    rules = rules_for(project)
    reqs = {r.id: r for r in db.query(DocumentRequirement).filter(DocumentRequirement.id.in_(rules.qualifications or [""]))}
    return ProviderEligibilityOut(
        provider_type=rules.provider_type,
        qualifications=[
            EligibilityQualification(id=q, name=reqs[q].name, description=reqs[q].description) for q in rules.qualifications if q in reqs
        ],
    )


def ineligibility_reasons(db: Session, project: Project, profile: ServiceProviderProfile) -> list[str]:
    """Why this provider can't respond to this requirement; empty = eligible.
    Platform verification itself is checked separately, by the callers'
    existing gates."""
    rules = rules_for(project)
    reasons = []
    if rules.provider_type == "organization" and profile.stakeholder_type != StakeholderType.organization:
        reasons.append("This requirement is open to providers registered as an organization only; your account is registered as an individual.")
    if rules.qualifications:
        names = {r.id: r.name for r in db.query(DocumentRequirement).filter(DocumentRequirement.id.in_(rules.qualifications))}
        held = {
            d.requirement_id: d
            for d in db.query(ServiceProviderDocument).filter(
                ServiceProviderDocument.service_provider_id == profile.user_id,
                ServiceProviderDocument.requirement_id.in_(rules.qualifications),
            )
        }
        today = date.today()
        for q in rules.qualifications:
            name = names.get(q, "a required qualification")
            doc = held.get(q)
            if not doc or doc.status != DocumentStatus.approved:
                reasons.append(f'This requirement needs a platform-approved "{name}"; your verification doesn\'t include an approved one.')
            elif doc.expires_on is not None and doc.expires_on < today:
                reasons.append(f'This requirement needs a valid "{name}"; yours expired on {doc.expires_on.isoformat()}.')
    return reasons


def assert_eligible(db: Session, project: Project, profile: ServiceProviderProfile) -> None:
    reasons = ineligibility_reasons(db, project, profile)
    if reasons:
        raise HTTPException(status_code=403, detail="You aren't eligible to respond to this requirement. " + " ".join(reasons))

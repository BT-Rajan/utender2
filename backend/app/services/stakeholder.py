"""Step 3: who a registered account represents.

A User is always a person (the login identity). Each marketplace side has a
profile row -- OwnerProfile / ServiceProviderProfile -- which is the
*stakeholder*: the identity that is verified and that every project, offer,
award and review is recorded under. The profile represents either the person
themselves (individual) or an Organization the person belongs to through an
OrganizationMembership.

The four states are kept distinct:
  account created         -> a User and its (empty) profile exist
  stakeholder established -> profile.stakeholder_type is set
  verified                -> profile.verification_status == approved
                             (for an organization: the organization is verified)
  eligible                -> profile.is_verified_active (owners: verified and
                             not suspended; service providers: also paid)
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.enums import MembershipRole, StakeholderType, UserRole, VerificationStatus
from app.models.organization import Organization, OrganizationMembership
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from app.services.audit import log_action

# Identity may only change while the profile is not under (or past) review --
# otherwise an approved individual could become an unverified organization.
from app.services.verification import EDITABLE_STATUSES  # noqa: E402


def stakeholder_profile(user: User, db: Session) -> OwnerProfile | ServiceProviderProfile | None:
    if user.role == UserRole.owner:
        return db.get(OwnerProfile, user.id)
    if user.role == UserRole.service_provider:
        return db.get(ServiceProviderProfile, user.id)
    return None


def membership_for(profile, user_id: str, db: Session) -> OrganizationMembership | None:
    if not profile.organization_id:
        return None
    return (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.organization_id == profile.organization_id, OrganizationMembership.user_id == user_id)
        .first()
    )


def display_name(profile, user: User) -> str | None:
    if isinstance(profile, ServiceProviderProfile):
        return profile.company_name  # the public trading name owners see on offers
    if profile.stakeholder_type == StakeholderType.organization and profile.organization:
        return profile.organization.legal_name
    return user.full_name


def describe(profile, user: User, db: Session, viewer_id: str | None = None) -> dict:
    """The stakeholder block shared by /account/identity and the admin views.
    viewer_id selects whose membership to report (defaults to the profile's
    own user, i.e. the founding representative)."""
    org = profile.organization if profile.organization_id else None
    organization = None
    if org:
        member_id = viewer_id or profile.user_id
        membership = membership_for(profile, member_id, db)
        representative = (
            db.query(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .filter(OrganizationMembership.organization_id == org.id, OrganizationMembership.role == MembershipRole.admin)
            .order_by(OrganizationMembership.created_at.asc())
            .first()
        )
        organization = {
            "id": org.id,
            "legal_name": org.legal_name,
            "member_count": len(org.memberships),
            "membership": {"role": membership.role.value, "position": membership.position} if membership else None,
            "authorized_representative": (
                {
                    "user_id": representative[1].id,
                    "full_name": representative[1].full_name,
                    "email": representative[1].email,
                    "position": representative[0].position,
                }
                if representative
                else None
            ),
        }
    verified = profile.verification_status == VerificationStatus.approved
    return {
        "id": profile.user_id,
        "side": user.role.value,
        "type": profile.stakeholder_type.value if profile.stakeholder_type else None,
        "display_name": display_name(profile, user),
        "organization": organization,
        "status": {
            "account_created": True,
            "stakeholder_established": profile.stakeholder_type is not None,
            "verified": verified,
            "eligible": profile.is_verified_active,
            "verification_status": profile.verification_status.value,
            "marketplace_status": profile.marketplace_status,
        },
        "editable": profile.verification_status in EDITABLE_STATUSES and not profile.is_suspended,
    }


def identity(user: User, db: Session) -> dict:
    profile = stakeholder_profile(user, db)
    person = {"user_id": user.id, "full_name": user.full_name, "email": user.email}
    if profile is None:  # admins act only as themselves
        return {"person": person, "role": user.role.value, "stakeholder": None, "acting_as": None}
    stakeholder = describe(profile, user, db, viewer_id=user.id)
    if stakeholder["type"] == StakeholderType.organization.value:
        acting_as = {"kind": "organization", "organization_id": stakeholder["organization"]["id"]}
    elif stakeholder["type"] == StakeholderType.individual.value:
        acting_as = {"kind": "individual", "user_id": user.id}
    else:
        acting_as = None  # not established yet
    if acting_as:
        # Every project/offer/review is recorded under the stakeholder id.
        acting_as |= {"stakeholder_id": profile.user_id, "name": stakeholder["display_name"]}
    return {"person": person, "role": user.role.value, "stakeholder": stakeholder, "acting_as": acting_as}


def establish(
    user: User,
    db: Session,
    stakeholder_type: StakeholderType,
    legal_name: str | None,
    position: str | None,
) -> None:
    profile = stakeholder_profile(user, db)
    if profile is None:
        raise HTTPException(status_code=403, detail="Only owner or service provider accounts represent a stakeholder.")
    if profile.verification_status not in EDITABLE_STATUSES or profile.is_suspended:
        raise HTTPException(
            status_code=409,
            detail="Who this account represents can't be changed while it is under review or after it has been verified.",
        )

    previous = profile.stakeholder_type.value if profile.stakeholder_type else None
    if stakeholder_type == StakeholderType.organization:
        name = (legal_name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="The organization's legal name is required.")
        position = (position or "").strip() or None
        if profile.organization_id:
            membership = membership_for(profile, user.id, db)
            if not membership or membership.role != MembershipRole.admin:
                raise HTTPException(status_code=403, detail="Only the organization's authorized representative can change it.")
            profile.organization.legal_name = name
            membership.position = position
        else:
            org = Organization(legal_name=name)
            db.add(org)
            db.flush()
            db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, role=MembershipRole.admin, position=position))
            profile.organization_id = org.id
        if isinstance(profile, ServiceProviderProfile):
            profile.company_name = name  # default trading name; editable when submitting for review
    else:
        _leave_organization(profile, user, db)
        if isinstance(profile, ServiceProviderProfile):
            profile.company_name = user.full_name or profile.company_name

    profile.stakeholder_type = stakeholder_type
    db.flush()
    log_action(
        db,
        actor_id=user.id,
        action="stakeholder.set",
        target_type=f"{user.role.value}_profile",
        target_id=user.id,
        previous_value=previous,
        new_value=stakeholder_type.value if stakeholder_type == StakeholderType.individual else f"organization:{legal_name}",
    )


def _leave_organization(profile, user: User, db: Session) -> None:
    if not profile.organization_id:
        return
    org = profile.organization
    membership = membership_for(profile, user.id, db)
    profile.organization_id = None
    db.flush()
    if membership:
        db.delete(membership)
        db.flush()
    db.refresh(org)
    if not org.memberships:
        db.delete(org)


def require_established(profile) -> None:
    """Verification operates on an established stakeholder."""
    if profile.stakeholder_type is None:
        raise HTTPException(
            status_code=400,
            detail="Tell us whether this account represents you personally or an organization before submitting for review.",
        )

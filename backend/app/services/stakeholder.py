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
import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.enums import MembershipRole, StakeholderType, UserRole, VerificationStatus
from app.models.organization import Organization, OrganizationInvitation, OrganizationMembership
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from app.services.audit import log_action
from app.services.email import notify_organization_invitation

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
    from app.services.team import acting_profile

    # A member of an organization acts as the organization's profile.
    profile = acting_profile(db, user)
    person = {"user_id": user.id, "full_name": user.full_name, "email": user.email}
    if profile is None:  # admins act only as themselves
        return {"person": person, "role": user.role.value, "stakeholder": None, "acting_as": None}
    stakeholder = describe(profile, profile.user if profile.user_id != user.id else user, db, viewer_id=user.id)
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
    joined = db.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
    if joined and profile.organization_id != joined.organization_id:
        # A member acts for the organization they were added to.
        raise HTTPException(status_code=409, detail="You act for an organization. Ask its representative to remove you first.")
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


# ---------- organization members ----------
# An organization is one stakeholder: one profile, verified once (Step 3).
# Its authorized representative (membership admin) invites colleagues by
# email; they join by accepting, signed in with that email;
# each colleague keeps their own login and acts as the organization's
# profile (services.team.acting_profile), so its verification, payment,
# trading name and everything recorded under it are shared. Their own
# (personal) profile is left untouched and unused while they are a member.


def _my_membership(user: User, db: Session) -> OrganizationMembership:
    membership = db.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
    if not membership:
        raise HTTPException(status_code=400, detail="This account doesn't act for an organization.")
    return membership


def _require_representative(user: User, db: Session) -> OrganizationMembership:
    membership = _my_membership(user, db)
    if membership.role != MembershipRole.admin:
        raise HTTPException(status_code=403, detail="Only the organization's authorized representative can manage its members.")
    return membership


def list_members(user: User, db: Session) -> list[dict]:
    membership = _my_membership(user, db)
    rows = (
        db.query(OrganizationMembership, User)
        .join(User, OrganizationMembership.user_id == User.id)
        .filter(OrganizationMembership.organization_id == membership.organization_id)
        .order_by(OrganizationMembership.created_at.asc(), User.email.asc())
        .all()
    )
    # The representative first, then everyone else in the order they joined.
    rows.sort(key=lambda row: row[0].role != MembershipRole.admin)
    return [
        {"user_id": u.id, "full_name": u.full_name, "email": u.email, "role": m.role.value, "position": m.position}
        for m, u in rows
    ]


INVITATION_DAYS = 14  # an unused invitation link stops working after this


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_can_join(target: User, db: Session) -> None:
    """The same rule as changing who an account represents: an account that
    already represents someone in its own right (established, under review or
    verified) stays as it is."""
    if db.query(OrganizationMembership).filter(OrganizationMembership.user_id == target.id).first():
        raise HTTPException(status_code=409, detail="That account already belongs to an organization.")
    own = stakeholder_profile(target, db)
    if own is None:
        raise HTTPException(status_code=400, detail="That account can't join an organization.")
    if own.verification_status not in EDITABLE_STATUSES or own.is_suspended or own.stakeholder_type is not None:
        raise HTTPException(status_code=409, detail="That account already represents someone in its own right, so it can't join.")


def invite_member(user: User, db: Session, email: str, position: str | None) -> tuple[OrganizationInvitation, str]:
    """Invite a colleague by email, account or not. Returns the invitation and
    its one-time token (the link is emailed; the representative may also
    share it directly)."""
    membership = _require_representative(user, db)
    email = email.strip().lower()
    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing:
        if (
            db.query(OrganizationMembership)
            .filter(OrganizationMembership.organization_id == membership.organization_id, OrganizationMembership.user_id == existing.id)
            .first()
        ):
            raise HTTPException(status_code=409, detail="That person is already a member.")
        if existing.role != user.role:
            raise HTTPException(status_code=400, detail="That account is on the other side of the marketplace.")
        _check_can_join(existing, db)
    now = datetime.utcnow()
    pending = (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.organization_id == membership.organization_id,
            OrganizationInvitation.email == email,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
            OrganizationInvitation.expires_at > now,
        )
        .first()
    )
    if pending:
        raise HTTPException(status_code=409, detail="An invitation to that email is already pending.")
    token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(
        organization_id=membership.organization_id,
        email=email,
        role=user.role,
        position=(position or "").strip() or None,
        token_hash=_hash(token),
        invited_by=user.id,
        expires_at=now + timedelta(days=INVITATION_DAYS),
    )
    db.add(invitation)
    db.flush()
    log_action(db, actor_id=user.id, action="organization.member_invited", target_type="organization", target_id=membership.organization_id, new_value=email)
    notify_organization_invitation(email, membership.organization.legal_name, user.full_name or user.email, token)
    return invitation, token


def pending_invitations(user: User, db: Session) -> list[OrganizationInvitation]:
    membership = _my_membership(user, db)
    return (
        db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.organization_id == membership.organization_id,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
            OrganizationInvitation.expires_at > datetime.utcnow(),
        )
        .order_by(OrganizationInvitation.created_at.asc())
        .all()
    )


def revoke_invitation(user: User, db: Session, invitation_id: str) -> None:
    membership = _require_representative(user, db)
    invitation = db.get(OrganizationInvitation, invitation_id)
    if not invitation or invitation.organization_id != membership.organization_id or invitation.accepted_at:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    invitation.revoked_at = datetime.utcnow()
    db.flush()


def _live_invitation(db: Session, token: str) -> OrganizationInvitation:
    invitation = db.query(OrganizationInvitation).filter(OrganizationInvitation.token_hash == _hash(token)).first()
    if not invitation or invitation.accepted_at or invitation.revoked_at or invitation.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=404, detail="This invitation is invalid, has expired or was withdrawn.")
    return invitation


def describe_invitation(db: Session, token: str) -> dict:
    """What the invitation link shows before signing in: who invites whom to what."""
    invitation = _live_invitation(db, token)
    inviter = db.get(User, invitation.invited_by) if invitation.invited_by else None
    return {
        "organization_name": invitation.organization.legal_name,
        "email": invitation.email,
        "role": invitation.role.value,
        "invited_by": (inviter.full_name or inviter.email) if inviter else None,
        "expires_at": invitation.expires_at,
        "account_exists": db.query(User.id).filter(func.lower(User.email) == invitation.email).first() is not None,
    }


def accept_invitation(user: User, db: Session, token: str) -> None:
    invitation = _live_invitation(db, token)
    if user.email.strip().lower() != invitation.email:
        raise HTTPException(status_code=403, detail="This invitation is for a different email address.")
    # The link carries a secret, but a link can be forwarded or shared on
    # purpose; the email on the account is then the only thing tying it to the
    # invited person -- so it has to be one the account holder has proved they
    # control. (Otherwise an account opened in advance with a colleague's
    # address would pass the match above.)
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email address before accepting this invitation.")
    if user.role != invitation.role:
        raise HTTPException(status_code=400, detail="This invitation is for an account on the other side of the marketplace.")
    _check_can_join(user, db)
    db.add(
        OrganizationMembership(
            organization_id=invitation.organization_id, user_id=user.id, role=MembershipRole.member, position=invitation.position
        )
    )
    invitation.accepted_at = datetime.utcnow()
    db.flush()
    log_action(db, actor_id=user.id, action="organization.member_joined", target_type="organization", target_id=invitation.organization_id, new_value=user.id)


def remove_member(user: User, db: Session, member_id: str) -> None:
    membership = _require_representative(user, db)
    if member_id == user.id:
        raise HTTPException(status_code=400, detail="You can't remove yourself as the organization's representative.")
    target = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.organization_id == membership.organization_id, OrganizationMembership.user_id == member_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Not a member of this organization.")
    # The organization's profile (its verification, payment and trading name)
    # is held by the account that established it. Removing that person would
    # leave their account still resolving to the organization's profile and so
    # still acting for it (and still receiving its emails), so it can't be
    # removed until the profile is moved to someone else.
    holds_profile = any(
        db.query(model.user_id).filter(model.organization_id == membership.organization_id, model.user_id == member_id).first()
        for model in (OwnerProfile, ServiceProviderProfile)
    )
    if holds_profile:
        raise HTTPException(
            status_code=409,
            detail="This person set up the organization and its profile is tied to their account, so they can't be removed.",
        )
    # They stop acting for the organization; it keeps everything recorded
    # under it. Their own account is as it was before they joined.
    db.delete(target)
    db.flush()
    log_action(
        db, actor_id=user.id, action="organization.member_removed", target_type="organization", target_id=membership.organization_id, previous_value=member_id
    )


def hand_over(user: User, db: Session, member_id: str) -> None:
    """Batch C: the authorized representative hands the role to another
    current member -- who then manages members and receives what the
    representative does -- and stays on as a member. The organization's
    records, verification and history are unchanged: they belong to the
    organization, not to whoever set it up."""
    _require_representative(user, db)
    # Security: under the representative's own row lock, so two hand-overs at
    # once can't leave the organization with two representatives.
    membership = db.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).populate_existing().with_for_update().first()
    if membership is None or membership.role != MembershipRole.admin:
        raise HTTPException(status_code=403, detail="Only the organization's authorized representative can manage its members.")
    if member_id == user.id:
        raise HTTPException(status_code=400, detail="You are already the organization's representative.")
    target = (
        db.query(OrganizationMembership)
        .filter(OrganizationMembership.organization_id == membership.organization_id, OrganizationMembership.user_id == member_id)
        .with_for_update()
        .first()
    )
    successor = db.get(User, member_id) if target else None
    if not target or successor is None or successor.deactivated_at is not None:
        raise HTTPException(status_code=404, detail="Not a member of this organization.")
    target.role, membership.role = MembershipRole.admin, MembershipRole.member
    db.flush()
    log_action(
        db, actor_id=user.id, action="organization.representative_changed", target_type="organization",
        target_id=membership.organization_id, previous_value=user.id, new_value=member_id,
    )

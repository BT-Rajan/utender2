"""Organization sharing: what a member does for their organization belongs to
the organization, so every current member works with it.

Records created while acting for an organization carry its id
(organization_id on projects, offers, offer documents and clarifications).
The access rule, used for every ownership check:

  record has an organization  -> its current members (OrganizationMembership)
  record has none             -> the person who created it

So a member who leaves loses access, and the organization keeps its work.
Each person still verifies as themselves (their own profile), so the
platform's verification and payment gates are unchanged.
"""
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.organization import OrganizationMembership
from app.models.project import Project
from app.models.user import User


def org_of(db: Session, user_id: str) -> str | None:
    row = db.query(OrganizationMembership.organization_id).filter(OrganizationMembership.user_id == user_id).first()
    return row[0] if row else None


def member_ids(db: Session, organization_id: str) -> list[str]:
    return [u for (u,) in db.query(OrganizationMembership.user_id).filter(OrganizationMembership.organization_id == organization_id)]


def team_ids(db: Session, user_id: str) -> list[str]:
    """The user and their organization's current members."""
    org = org_of(db, user_id)
    return [user_id] + sorted(set(member_ids(db, org)) - {user_id}) if org else [user_id]


def can_access(db: Session, user: User, organization_id: str | None, creator_id: str | None) -> bool:
    if organization_id:
        return org_of(db, user.id) == organization_id
    return creator_id in (user.id, acting_id(db, user))


def owns(db: Session, user: User, project: Project) -> bool:
    """The requirement's owner side: its organization's members, or (for an
    individual's requirement) the owner."""
    return can_access(db, user, project.organization_id, project.owner_id)


def mine(db: Session, user: User, model, creator_col):
    """SQL condition: rows of `model` this user's side owns (see can_access)."""
    org = org_of(db, user.id)
    personal = and_(model.organization_id.is_(None), creator_col.in_({user.id, acting_id(db, user)}))
    return or_(model.organization_id == org, personal) if org else personal


def side_of(db: Session, organization_id: str | None, creator_id: str | None) -> list[str]:
    """The user ids standing for a record: its organization's members, or its creator."""
    if organization_id:
        return member_ids(db, organization_id)
    return [creator_id] if creator_id else []


def side_users(db: Session, organization_id: str | None, creator_id: str | None) -> list[User]:
    ids = side_of(db, organization_id, creator_id)
    return db.query(User).filter(User.id.in_(ids)).all() if ids else []


def acting_profile(db: Session, user: User):
    """The stakeholder this person acts as: their organization's profile (the
    one the organization was established and verified with) when they are a
    member, otherwise their own. Verification, payment, trading name and
    every record they create belong to it."""
    from app.models.enums import UserRole
    from app.models.owner import OwnerProfile
    from app.models.service_provider import ServiceProviderProfile

    model = OwnerProfile if user.role == UserRole.owner else ServiceProviderProfile if user.role == UserRole.service_provider else None
    if model is None:
        return None
    org = org_of(db, user.id)
    if org:
        profile = db.query(model).filter(model.organization_id == org).first()
        if profile:
            return profile
    return db.get(model, user.id)


def acting_id(db: Session, user: User) -> str:
    profile = acting_profile(db, user)
    return profile.user_id if profile else user.id

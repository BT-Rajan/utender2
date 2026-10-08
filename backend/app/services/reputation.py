"""Stage 8.7/8.8: a party's U-Tender reputation, read live from the
authoritative records -- transactions completed under Stage 7 (the one
definition of "completed") and the owner reviews recorded on them (8.3-8.5).
Informational only: nothing here feeds eligibility, verification, ordering
or award. Reviews are shown without the reviewer, the requirement or any
other detail of the transaction they came from (8.6). Both parties are
stakeholder profile ids -- the organisation's, which requirements, offers,
awards and reviews are recorded under -- never an employee's."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agreement import Agreement
from app.models.award_record import AwardRecord
from app.models.review import Review
from app.models.service_provider import ServiceProviderProfile
from app.models.project import Project
from app.schemas.review import OwnerReputationOut, ProviderReputationOut
from app.services.reviews import OWNER_TO_PROVIDER, PROVIDER_TO_OWNER

RECENT_REVIEWS = 5


def _reviews(db: Session, party_filter, direction: str, recent: bool):
    """(count, simple average or None, latest reviews) of one party's reviews in one direction."""
    where = (party_filter, Review.direction == direction, Review.hidden_at.is_(None))  # Stage 8.15: hidden reviews don't count
    count, average = db.query(func.count(Review.id), func.avg(Review.rating)).filter(*where).one()
    latest = db.query(Review).filter(*where).order_by(Review.created_at.desc(), Review.id).limit(RECENT_REVIEWS).all() if recent and count else []
    return count, round(float(average), 1) if count else None, latest  # no reviews is "none yet", never 0 stars


def provider_reputation(db: Session, service_provider_id: str) -> ProviderReputationOut:
    """service_provider_id always comes from the server's own records, never the request."""
    profile = db.get(ServiceProviderProfile, service_provider_id)
    completed = (
        db.query(func.count(Agreement.id))
        .join(AwardRecord, AwardRecord.id == Agreement.award_id)
        .filter(AwardRecord.service_provider_id == service_provider_id, Agreement.status == "completed")
        .scalar()
    )
    count, average, recent = _reviews(db, Review.service_provider_id == service_provider_id, OWNER_TO_PROVIDER, True)
    return ProviderReputationOut(
        company_name=profile.company_name if profile else None,
        completed_transactions=completed,
        review_count=count,
        avg_rating=average,
        recent_reviews=recent,
    )


def owner_reputation(db: Session, owner_id: str, *, with_reviews: bool) -> OwnerReputationOut:
    """owner_id (a requirement's owner_id) always comes from the server's own records."""
    completed = (
        db.query(func.count(Agreement.id))
        .join(Project, Project.id == Agreement.project_id)
        .filter(Project.owner_id == owner_id, Agreement.status == "completed")
        .scalar()
    )
    count, average, recent = _reviews(db, Review.owner_id == owner_id, PROVIDER_TO_OWNER, with_reviews)
    return OwnerReputationOut(completed_transactions=completed, review_count=count, avg_rating=average, recent_reviews=recent)


def completed_together(db: Session, owner_id: str, provider_ids) -> dict[str, int]:
    """Stage 8.12: how many transactions this owner organisation has completed
    with each of these providers -- from the authoritative Stage 7 completion
    only (never an offer, a lost or cancelled tender, or unfinished work). One
    grouped query; informational, never used to order or judge offers."""
    ids = list(set(provider_ids))
    if not ids:
        return {}
    rows = (
        db.query(AwardRecord.service_provider_id, func.count(Agreement.id))
        .join(Agreement, Agreement.award_id == AwardRecord.id)
        .join(Project, Project.id == AwardRecord.project_id)
        .filter(Project.owner_id == owner_id, Agreement.status == "completed", AwardRecord.service_provider_id.in_(ids))
        .group_by(AwardRecord.service_provider_id)
        .all()
    )
    return dict(rows)


def previous_providers(db: Session, owner_id: str) -> list[dict]:
    """Stage 8.12: the providers this owner organisation has completed work
    with, each once, with its own completed requirements (title and date
    only), latest first. The owner side's own history, for it alone."""
    rows = (
        db.query(AwardRecord.service_provider_id, ServiceProviderProfile.company_name, Project.id, Project.title, Agreement.completed_at)
        .join(Agreement, Agreement.award_id == AwardRecord.id)
        .join(Project, Project.id == AwardRecord.project_id)
        .outerjoin(ServiceProviderProfile, ServiceProviderProfile.user_id == AwardRecord.service_provider_id)
        .filter(Project.owner_id == owner_id, Agreement.status == "completed")
        .order_by(Agreement.completed_at.desc(), Project.id)
        .all()
    )
    providers: dict[str, dict] = {}
    for provider_id, name, project_id, title, completed_at in rows:
        entry = providers.setdefault(provider_id, {"company_name": name, "transactions": []})
        entry["transactions"].append({"project_id": project_id, "title": title, "completed_at": completed_at})
    return [{"company_name": e["company_name"], "completed_transactions": len(e["transactions"]),
             "last_completed_at": e["transactions"][0]["completed_at"], "transactions": e["transactions"]} for e in providers.values()]


def previous_owners(db: Session, service_provider_id: str) -> list[dict]:
    """Stage 8.13: the owners this provider organisation has completed U-Tender
    work for (Stage 7 completion only), each once, with those requirements
    (title and date). Names only -- the organisation's legal name or the
    individual's name it already saw on award (Stage 7.2), never an email,
    phone or any other contact detail -- and only for that provider."""
    from app.models.organization import Organization
    from app.models.user import User

    rows = (
        db.query(Project.owner_id, Organization.legal_name, User.full_name, Project.id, Project.title, Agreement.completed_at)
        .join(AwardRecord, AwardRecord.project_id == Project.id)
        .join(Agreement, Agreement.award_id == AwardRecord.id)
        .outerjoin(Organization, Organization.id == Project.organization_id)
        .outerjoin(User, User.id == Project.owner_id)
        .filter(AwardRecord.service_provider_id == service_provider_id, Agreement.status == "completed")
        .order_by(Agreement.completed_at.desc(), Project.id)
        .all()
    )
    owners: dict[str, dict] = {}
    for owner_id, org_name, person, project_id, title, completed_at in rows:
        entry = owners.setdefault(owner_id, {"owner_name": org_name or person, "transactions": []})
        entry["transactions"].append({"project_id": project_id, "title": title, "completed_at": completed_at})
    return [{"owner_name": e["owner_name"], "completed_transactions": len(e["transactions"]),
             "last_completed_at": e["transactions"][0]["completed_at"], "transactions": e["transactions"]} for e in owners.values()]


def completed_counts(db: Session, provider_ids) -> dict[str, int]:
    """Stage 8.14: each provider's completed U-Tender transactions (the same
    count as provider_reputation), for a page of offers in one grouped query."""
    ids = list(set(provider_ids))
    if not ids:
        return {}
    return dict(
        db.query(AwardRecord.service_provider_id, func.count(Agreement.id))
        .join(Agreement, Agreement.award_id == AwardRecord.id)
        .filter(AwardRecord.service_provider_id.in_(ids), Agreement.status == "completed")
        .group_by(AwardRecord.service_provider_id)
        .all()
    )

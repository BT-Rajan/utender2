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
    where = (party_filter, Review.direction == direction)
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

"""Stage 8.7: a service provider's U-Tender reputation, read live from the
authoritative records -- transactions completed under Stage 7 (the one
definition of "completed") and the owner reviews recorded on them (8.3-8.5).
Informational only: nothing here feeds eligibility, verification, ordering
or award. Owner reviews are shown without the owner, the requirement or any
other detail of the transaction they came from (8.6)."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agreement import Agreement
from app.models.award_record import AwardRecord
from app.models.review import Review
from app.models.service_provider import ServiceProviderProfile
from app.schemas.review import ProviderReputationOut
from app.services.reviews import OWNER_TO_PROVIDER

RECENT_REVIEWS = 5


def provider_reputation(db: Session, service_provider_id: str) -> ProviderReputationOut:
    """service_provider_id is the provider stakeholder's profile id -- the
    organisation's, which offers, awards and reviews are recorded under --
    always taken from the server's own records, never from the request."""
    profile = db.get(ServiceProviderProfile, service_provider_id)
    completed = (
        db.query(func.count(Agreement.id))
        .join(AwardRecord, AwardRecord.id == Agreement.award_id)
        .filter(AwardRecord.service_provider_id == service_provider_id, Agreement.status == "completed")
        .scalar()
    )
    owner_reviews = (Review.service_provider_id == service_provider_id, Review.direction == OWNER_TO_PROVIDER)
    count, average = db.query(func.count(Review.id), func.avg(Review.rating)).filter(*owner_reviews).one()
    recent = db.query(Review).filter(*owner_reviews).order_by(Review.created_at.desc(), Review.id).limit(RECENT_REVIEWS).all()
    return ProviderReputationOut(
        company_name=profile.company_name if profile else None,
        completed_transactions=completed,
        review_count=count,
        avg_rating=round(float(average), 1) if count else None,  # no reviews is "none yet", never 0 stars
        recent_reviews=recent,
    )

"""Stage 8.3/8.4: one review per completed transaction in each direction --
the owner side reviewing the winning provider, the winning provider's side
reviewing the owner. Callers authorize their side and hold the requirement's
lock; this records the review against the transaction's own parties (never
ids from the request), keeps the provider's public rating in step, writes the
audit entry in the same transaction, and tells the reviewed party."""
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.award_record import AwardRecord
from app.models.enums import NotificationType
from app.models.offer import Offer
from app.models.project import Project
from app.models.review import Review
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from app.services import audit
from app.services import notify as notify_service
from app.services.transactions import completed_transaction

logger = logging.getLogger(__name__)

OWNER_TO_PROVIDER = "owner_to_provider"
PROVIDER_TO_OWNER = "provider_to_owner"


def review_of(db: Session, project_id: str, direction: str) -> Review | None:
    return db.query(Review).filter(Review.project_id == project_id, Review.direction == direction).first()


def record_review(db: Session, project: Project, direction: str, reviewer: User, rating: int, comment: str | None) -> Review:
    # Stage 8.1: a review rests on completed work -- the transaction closed by
    # the owner side's acceptance (Stage 7.11) -- never on the award alone.
    agreement = completed_transaction(db, project.id)
    if agreement is None:
        if direction == OWNER_TO_PROVIDER:
            raise HTTPException(status_code=400, detail="You can review the service provider once the work has been accepted and the transaction is completed.")
        raise HTTPException(status_code=400, detail="You can review the owner once the work has been accepted and the transaction is completed.")
    if review_of(db, project.id, direction):
        raise HTTPException(status_code=409, detail="This transaction has already been reviewed (by a colleague or from another tab). This page now shows the latest.")
    # The parties come from the transaction's own records, never the request:
    # the requirement's owner stakeholder and the award's provider (the PASS 17
    # IDOR fix, now for both directions).
    award = db.query(AwardRecord).filter(AwardRecord.project_id == project.id).first()
    review = Review(
        project_id=project.id,
        owner_id=project.owner_id,
        service_provider_id=award.service_provider_id,
        direction=direction,
        reviewer_id=reviewer.id,
        rating=rating,
        comment=(comment or "").strip() or None,
    )
    db.add(review)
    db.flush()
    if direction == OWNER_TO_PROVIDER:
        # Recompute the provider's public average from its owner reviews rather
        # than trusting an incrementally-maintained counter.
        ratings = [r for (r,) in db.query(Review.rating).filter(
            Review.service_provider_id == award.service_provider_id, Review.direction == OWNER_TO_PROVIDER)]
        profile = db.get(ServiceProviderProfile, award.service_provider_id)
        if profile:
            profile.review_count = len(ratings)
            profile.avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
    # log_action commits: the review, the rating and the audit entry land together.
    audit.log_action(db, actor_id=reviewer.id, action=f"review.{direction}", target_type="project", target_id=project.id,
                     new_value=f"{review.id} rating:{review.rating} owner:{review.owner_id} service_provider:{review.service_provider_id}")
    db.refresh(review)
    _tell(db, project, award, direction)
    return review


def _tell(db: Session, project: Project, award: AwardRecord, direction: str) -> None:
    """The reviewed party is told a review was recorded -- best-effort, after
    the commit; a failure never undoes the review. Its content isn't in the
    notification (who sees reviews is a later step)."""
    try:
        if direction == OWNER_TO_PROVIDER:
            winner = db.get(Offer, award.offer_id)
            notify_service.notify_team(
                db, db.get(User, award.service_provider_id), NotificationType.review_received,
                link=f"/service-provider/projects/{project.id}/offer", organization_id=winner.organization_id if winner else None,
                project_title=project.title, party="owner", party_ar="المالك",
            )
        else:
            notify_service.notify_team(
                db, db.get(User, project.owner_id), NotificationType.review_received,
                link=f"/owner/projects/{project.id}", organization_id=project.organization_id,
                project_title=project.title, party="service provider", party_ar="مقدم الخدمة",
            )
    except Exception:  # noqa: BLE001 -- notifying must never undo or fail the review
        db.rollback()
        logger.exception("Could not send review notification for %s", project.id)

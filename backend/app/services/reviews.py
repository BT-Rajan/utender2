"""Stage 8.3/8.4: one review per completed transaction in each direction --
the owner side reviewing the winning provider, the winning provider's side
reviewing the owner. Callers authorize their side and hold the requirement's
lock; this records the review against the transaction's own parties (never
ids from the request), keeps the provider's public rating in step, writes the
audit entry in the same transaction, and tells the reviewed party."""
import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.award_record import AwardRecord
from app.models.enums import NotificationType
from app.models.offer import Offer
from app.models.project import Project
from app.models.review import Review, ReviewReport
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from app.services import audit
from app.services import notify as notify_service
from app.services.transactions import completed_transaction

logger = logging.getLogger(__name__)

OWNER_TO_PROVIDER = "owner_to_provider"
PROVIDER_TO_OWNER = "provider_to_owner"


# Stage 8.15: why a party may report a review or response -- policy, not disagreement.
REPORT_REASONS = ("abusive", "private_information", "not_about_this_transaction", "other")


def review_of(db: Session, project_id: str, direction: str) -> Review | None:
    """The review on record in one direction, hidden or not -- what the
    one-review rule and the reviewer's own view rest on."""
    return db.query(Review).filter(Review.project_id == project_id, Review.direction == direction).first()


def shown_review_of(db: Session, project_id: str, direction: str) -> Review | None:
    """Stage 8.15: the review as others may see it -- none once an admin has hidden it."""
    review = review_of(db, project_id, direction)
    return review if review is not None and review.hidden_at is None else None


def _recount_provider(db: Session, profile: ServiceProviderProfile | None, service_provider_id: str) -> None:
    """The provider's stored public rating, recomputed from its shown owner
    reviews (never an incremental counter). The caller holds the profile row."""
    if profile is None:
        return
    ratings = [r for (r,) in db.query(Review.rating).filter(
        Review.service_provider_id == service_provider_id, Review.direction == OWNER_TO_PROVIDER, Review.hidden_at.is_(None))]
    profile.review_count = len(ratings)
    profile.avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0


def _lock_provider(db: Session, service_provider_id: str) -> ServiceProviderProfile | None:
    return db.query(ServiceProviderProfile).filter(ServiceProviderProfile.user_id == service_provider_id).with_for_update().first()


def record_review(db: Session, project: Project, direction: str, reviewer: User, rating: int, comment: str | None) -> Review:
    # Stage 8.5: a requirement an admin has suspended takes no new review, from either side.
    if project.is_suspended:
        raise HTTPException(status_code=400, detail="This requirement is suspended.")
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
    profile = None
    if direction == OWNER_TO_PROVIDER:
        # Stage 8.10: owners of different requirements may review the same
        # provider at once. Taking its profile row first (after the
        # requirement's lock, always in that order) queues them, so each
        # recount below sees the reviews before it -- without it they
        # deadlocked on the row or stored a stale rating.
        profile = _lock_provider(db, award.service_provider_id)
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
        _recount_provider(db, profile, award.service_provider_id)
    # log_action commits: the review, the rating and the audit entry land together.
    audit.log_action(db, actor_id=reviewer.id, action=f"review.{direction}", target_type="project", target_id=project.id,
                     new_value=f"{review.id} rating:{review.rating} owner:{review.owner_id} service_provider:{review.service_provider_id}")
    db.refresh(review)
    _tell(db, project, award, to_provider=direction == OWNER_TO_PROVIDER, kind=NotificationType.review_received)
    return review


def record_response(db: Session, project: Project, direction: str, responder: User, text: str) -> Review:
    """Stage 8.9: the reviewed side's one, final response to the review in
    `direction` -- beside the review, never changing its rating, comment or
    parties, so neither side's reputation moves. Callers authorize the
    reviewed side and hold the requirement's lock; the responding party is
    the review's own subject, never one named in the request."""
    if project.is_suspended:
        raise HTTPException(status_code=400, detail="This requirement is suspended.")
    review = shown_review_of(db, project.id, direction)  # Stage 8.15: not to one an admin has hidden
    if review is None:
        raise HTTPException(status_code=404, detail="There is no review to respond to.")
    if review.response is not None:
        raise HTTPException(status_code=409, detail="This review already has a response (from a colleague or another tab). This page now shows the latest.")
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Write a response first.")
    review.response = text
    review.response_at = datetime.utcnow().replace(microsecond=0)
    review.responded_by = responder.id
    # log_action commits: the response and its audit entry land together.
    audit.log_action(db, actor_id=responder.id, action=f"review.response.{direction}", target_type="project", target_id=project.id,
                     new_value=f"{review.id}")
    db.refresh(review)
    award = db.query(AwardRecord).filter(AwardRecord.project_id == project.id).first()
    # The reviewer's side is told; the reviewed side wrote it, so no loop.
    _tell(db, project, award, to_provider=direction == PROVIDER_TO_OWNER, kind=NotificationType.review_response)
    return review


def report(db: Session, project: Project, direction: str, target: str, reporter: User, reason: str, note: str | None) -> ReviewReport:
    """Stage 8.15: report the review in `direction` (target "review" -- callers
    pass the direction their side received) or the response to it (target
    "response" -- the direction their side wrote). Callers authorize the side
    and hold the requirement's lock. A report is a signal for an admin only:
    the review, its response and every rating stay exactly as they are."""
    if reason not in REPORT_REASONS:
        raise HTTPException(status_code=400, detail="Choose why you are reporting this.")
    review = shown_review_of(db, project.id, direction)
    if review is None or (target == "response" and review.shown_response is None):
        raise HTTPException(status_code=404, detail="There is nothing to report.")
    if db.query(ReviewReport.id).filter(ReviewReport.review_id == review.id, ReviewReport.target == target).first():
        raise HTTPException(status_code=409, detail="This has already been reported; U-Tender is looking at it.")
    entry = ReviewReport(review_id=review.id, target=target, reporter_id=reporter.id, reason=reason, note=(note or "").strip() or None)
    db.add(entry)
    db.flush()
    audit.log_action(db, actor_id=reporter.id, action=f"review.report.{target}", target_type="project", target_id=project.id,
                     new_value=f"{entry.id} review:{review.id} reason:{reason}")
    db.refresh(entry)
    return entry


def moderate(db: Session, entry: ReviewReport, admin: User, decision: str, note: str | None) -> ReviewReport:
    """Stage 8.15: an admin's decision on an open report -- keep what was
    reported, or hide it. Hiding keeps the row (reviewer, parties, rating,
    text) and the audit says who and why; a hidden review stops being shown or
    counted (the provider's stored rating is recomputed under its lock), a
    hidden response stops being shown. Nothing else changes."""
    from app.services.tender_lifecycle import lock_project

    if decision not in ("keep", "hide"):
        raise HTTPException(status_code=400, detail="Choose to keep or hide it.")
    review = db.get(Review, entry.review_id)
    lock_project(db, review.project_id)  # the same order as every review write: the requirement, then the provider
    db.refresh(entry)
    if entry.status != "open":
        raise HTTPException(status_code=409, detail="This report has already been decided. This page now shows the latest.")
    db.refresh(review)
    now = datetime.utcnow().replace(microsecond=0)
    if decision == "hide":
        if entry.target == "response":
            review.response_hidden_at = review.response_hidden_at or now
        elif review.hidden_at is None:
            profile = _lock_provider(db, review.service_provider_id) if review.direction == OWNER_TO_PROVIDER else None
            review.hidden_at = now
            db.flush()
            if review.direction == OWNER_TO_PROVIDER:
                _recount_provider(db, profile, review.service_provider_id)
    entry.status = "hidden" if decision == "hide" else "kept"
    entry.resolved_by, entry.resolved_at = admin.id, now
    entry.resolution_note = (note or "").strip() or None
    audit.log_action(db, actor_id=admin.id, action=f"review.moderation.{decision}", target_type="project", target_id=review.project_id,
                     previous_value=f"{entry.id} {entry.target} of review:{review.id}", new_value=entry.status)
    db.refresh(entry)
    return entry


def _tell(db: Session, project: Project, award: AwardRecord, *, to_provider: bool, kind: NotificationType) -> None:
    """The other side is told a review (or a response, 8.9) was recorded --
    best-effort, after the commit; a failure never undoes it. Its content
    isn't in the notification; each side reads it on its transaction page
    (Stage 8.6)."""
    try:
        if to_provider:
            winner = db.get(Offer, award.offer_id)
            notify_service.notify_team(
                db, db.get(User, award.service_provider_id), kind,
                link=f"/service-provider/projects/{project.id}/offer", organization_id=winner.organization_id if winner else None,
                project_title=project.title, party="owner", party_ar="المالك",
            )
        else:
            notify_service.notify_team(
                db, db.get(User, project.owner_id), kind,
                link=f"/owner/projects/{project.id}", organization_id=project.organization_id,
                project_title=project.title, party="service provider", party_ar="مقدم الخدمة",
            )
    except Exception:  # noqa: BLE001 -- notifying must never undo or fail the review
        db.rollback()
        logger.exception("Could not send review notification for %s", project.id)

"""Stage 6.10: clarifying a submitted offer during evaluation -- the owner's
side asks, the offer's provider side answers -- on the existing
clarifications record (offer_id set). Private to the two sides. An answer is
text beside the offer: it never changes the offer (a formal change is a
Stage 5 revision, which isn't possible once offers have closed)."""
from sqlalchemy.orm import Session

from app.models.clarification import Clarification
from app.models.enums import OfferStatus, ProjectStatus
from app.models.offer import Offer
from app.models.project import Project
from app.models.user import User
from app.schemas.clarification import OfferClarificationOut

# Evaluation: offers have closed and no outcome is recorded yet.
EVALUATION = (ProjectStatus.closed, ProjectStatus.under_evaluation)


def closed_reason(project: Project, offer: Offer) -> str | None:
    """Why this offer can't be clarified now (asked or answered), or None."""
    if project.is_suspended:
        return "This requirement has been suspended by an admin."
    if project.status not in EVALUATION:
        return "Offers can be clarified only while they are being evaluated: after offers close and before the requirement's outcome."
    if offer.status != OfferStatus.submitted:
        return "This offer is no longer live."
    if offer.is_suspended:
        return "This offer has been suspended by an admin and cannot be clarified."
    return None


def _name(db: Session, user_id: str | None) -> str | None:
    user = db.get(User, user_id) if user_id else None
    return (user.full_name or user.email) if user else None


def clarification_out(db: Session, c: Clarification, owner_side: bool) -> OfferClarificationOut:
    return OfferClarificationOut(
        id=c.id, project_id=c.project_id, offer_id=c.offer_id, offer_revision=c.offer_revision,
        question=c.question, asked_at=c.created_at, asked_by_name=_name(db, c.asked_by) if owner_side else None,
        answer=c.answer, answered_at=c.answered_at, answered_by_name=_name(db, c.answered_by),
    )


def offer_clarifications(db: Session, offer: Offer, owner_side: bool) -> list[OfferClarificationOut]:
    rows = db.query(Clarification).filter(Clarification.offer_id == offer.id).order_by(Clarification.created_at.asc(), Clarification.id)
    return [clarification_out(db, c, owner_side) for c in rows]

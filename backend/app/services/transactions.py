from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.agreement import Agreement, Milestone

# Batch D: how long work handed to the owner side (the whole work submitted as
# complete, or a deliverable delivered) may wait for its answer before the
# provider may walk away without that counting against it.
ANSWER_DAYS = 30


def unanswered_delivery(db: Session, agreement: Agreement, at: datetime | None = None) -> bool:
    """Whether a deliverable had been waiting ANSWER_DAYS for the owner side's
    accept-or-return at `at` (now by default). The whole work can't be
    submitted until every deliverable is accepted, so an owner who never
    answers one would otherwise hold the provider there for good."""
    at = at or datetime.utcnow()
    return db.query(Milestone.id).filter(
        Milestone.agreement_id == agreement.id, Milestone.status == "delivered", Milestone.delivered_at <= at - timedelta(days=ANSWER_DAYS)
    ).first() is not None


def completed_transaction(db: Session, project_id: str) -> Agreement | None:
    """Stage 8.1: the one completion point the trust and reputation journey
    builds on -- the award's agreement closed by the owner side's acceptance
    of the whole work (Stage 7.10/7.11: status "completed", completed_at at
    server time, written once and never reopened). Anything short of it --
    awarded, in force, executing, on hold, delivered or submitted awaiting
    acceptance, returned for correction -- or any other ending (terminated,
    cancelled, no award, expired, closed externally) is not a completed
    transaction."""
    return db.query(Agreement).filter(Agreement.project_id == project_id, Agreement.status == "completed").first()

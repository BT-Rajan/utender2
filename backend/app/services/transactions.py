from sqlalchemy.orm import Session

from app.models.agreement import Agreement


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

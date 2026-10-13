from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.agreement import Agreement, Milestone

# Batch D: how long work handed to the owner side (the whole work submitted as
# complete, or a deliverable delivered) may wait for its answer before the
# provider may walk away without that counting against it.
ANSWER_DAYS = 30


# Audit actions that stop the owner side from answering, and the ones that
# end that stop: an admin suspending the requirement, suspending the owner
# account, or deactivating the owner's login.
_PAUSES = {
    "project": ("project.suspend", "project.reactivate"),
    "owner": ("owner.suspend", "owner.reactivate"),
    "account": ("account.deactivate", "account.reactivate"),
}


def _intervals(db: Session, target_id: str, start_action: str, end_action: str, until: datetime) -> list[tuple[datetime, datetime]]:
    from app.models.audit_log import AuditLog

    out, started = [], None
    for action, at in db.query(AuditLog.action, AuditLog.created_at).filter(
        AuditLog.target_id == target_id, AuditLog.action.in_((start_action, end_action)), AuditLog.created_at <= until,
    ).order_by(AuditLog.created_at.asc(), AuditLog.id.asc()):
        if action == start_action and started is None:
            started = at
        elif action == end_action and started is not None:
            out.append((started, at))
            started = None
    if started is not None:  # still stopped
        out.append((started, until))
    return out


def suspended_for(db: Session, project_id: str, since: datetime, until: datetime | None = None) -> timedelta:
    """How long, between `since` and `until` (now), the owner side could not
    answer because an admin had the requirement suspended, or the owner
    account suspended or deactivated -- from the audit log. That time doesn't
    count towards how long work has waited for the owner side's answer.
    Overlapping stops count once."""
    from app.models.project import Project

    until = until or datetime.utcnow()
    owner_id = db.query(Project.owner_id).filter(Project.id == project_id).scalar()
    spans = _intervals(db, project_id, *_PAUSES["project"], until)
    if owner_id:
        spans += _intervals(db, owner_id, *_PAUSES["owner"], until)
        spans += _intervals(db, owner_id, *_PAUSES["account"], until)
    total, edge = timedelta(0), since
    for start, end in sorted(spans):
        start, end = max(start, edge), min(end, until)
        if end > start:
            total += end - start
            edge = end
    return total


def waited_long_enough(db: Session, project_id: str, since: datetime | None, at: datetime | None = None) -> bool:
    """Whether work handed to the owner side at `since` has waited ANSWER_DAYS
    for its answer by `at` (now), not counting time the requirement was suspended."""
    if since is None:
        return False
    at = at or datetime.utcnow()
    return at - since - suspended_for(db, project_id, since, at) >= timedelta(days=ANSWER_DAYS)


def unanswered_delivery(db: Session, agreement: Agreement, at: datetime | None = None) -> bool:
    """Whether a deliverable had been waiting ANSWER_DAYS for the owner side's
    accept-or-return at `at` (now by default). The whole work can't be
    submitted until every deliverable is accepted, so an owner who never
    answers one would otherwise hold the provider there for good."""
    at = at or datetime.utcnow()
    waiting = db.query(Milestone.delivered_at).filter(
        Milestone.agreement_id == agreement.id, Milestone.status == "delivered", Milestone.delivered_at <= at - timedelta(days=ANSWER_DAYS)
    ).all()
    return any(waited_long_enough(db, agreement.project_id, delivered_at, at) for (delivered_at,) in waiting)


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

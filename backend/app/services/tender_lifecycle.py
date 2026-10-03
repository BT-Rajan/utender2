from datetime import datetime

from sqlalchemy.orm import Session

from app.models.enums import OfferStatus, ProjectStatus, TenderType
from app.models.offer import Offer
from app.models.project import Project


# The single predicate behind the sealed-bid privacy rule (spec §19-21,
# D-001): while true, bidder identity/amount/message must never reach the
# owner through ANY endpoint — offers list, offer history, notifications,
# email, or clarifications. Centralized here so every call site (owner.py's
# offers list/history, clarifications.py's Q&A list) shares one definition
# instead of each re-deriving it and risking drift.
#
# A sealed tender opens when its DEADLINE passes — not when its status
# happens to change. Keying on status alone (== open) let an owner cancel a
# sealed tender before the deadline and read every bid, because "canceled"
# isn't "open". So the seal holds for open AND canceled tenders until the
# deadline, and the deadline itself (not the lazily-synced status) is what
# lifts it. (The name predates this; it means "bids are still sealed".)
def is_sealed_and_open(project: Project) -> bool:
    return (
        project.tender_type == TenderType.sealed
        and project.status in (ProjectStatus.open, ProjectStatus.canceled)
        and project.bid_deadline > datetime.utcnow()
    )


# Bidding is open only while the tender is "open" AND the deadline hasn't
# passed — the instant of the deadline itself is closed, matching
# sync_expired_projects (<=) and publish (<=). Judged on the server clock;
# nothing the client sends is consulted.
def bidding_is_open(project: Project) -> bool:
    return project.status == ProjectStatus.open and project.bid_deadline > datetime.utcnow()


# SELECT ... FOR UPDATE on the tender row. Every operation that can change
# whether bids are acceptable — submit, withdraw, close, cancel, evaluate,
# award, amend — takes THIS lock first (always before any offer row, so lock
# order is the same everywhere and can't deadlock), then re-reads and checks
# the state under it. That makes "bid arrives as the owner closes" and "two
# awards at once" resolve to one clear winner instead of both passing a stale
# check. populate_existing so an already-loaded copy is refreshed, not reused.
# (SQLite, used by most tests, ignores FOR UPDATE; the guarantee is MySQL's.)
def lock_project(db: Session, project_id: str) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).populate_existing().with_for_update().first()


# Bidding isn't cron-driven — a project's deadline passing is detected
# lazily, the first time anything reads it, and written through so the
# stored status is never stale for more than one request. Only 'open'
# projects past their deadline ever move here; every other status
# (draft, under_evaluation, awarded, no_award, canceled, expired itself)
# is either not yet started or already terminal/owner-driven, so this
# never fights a manual lifecycle action.
def sync_expired_projects(db: Session) -> None:
    now = datetime.utcnow()
    # skip_locked: a row another request is transitioning right now (owner
    # cancel/award, say) is left alone instead of overwritten with a stale
    # closed/expired — the next read picks it up if it's still open.
    stale = (
        db.query(Project)
        .filter(Project.status == ProjectStatus.open, Project.bid_deadline <= now)
        .with_for_update(skip_locked=True)
        .all()
    )
    if not stale:
        return
    for project in stale:
        has_live_offer = (
            db.query(Offer.id)
            .filter(Offer.project_id == project.id, Offer.status == OfferStatus.submitted)
            .first()
            is not None
        )
        # closed: at least one live bid, waiting on the owner to evaluate.
        # expired: nobody bid (or every bid was withdrawn) — nothing to
        # evaluate, so it never needs an owner decision to leave "open".
        project.status = ProjectStatus.closed if has_live_offer else ProjectStatus.expired
    db.commit()

from datetime import datetime

from sqlalchemy import text
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
def db_now(db: Session) -> datetime:
    """The database's current UTC time -- one clock for every app server, so
    deadline decisions don't depend on which server took the request. (SQLite,
    used by most tests, has no separate server: the app clock is the same.)"""
    if db.get_bind().dialect.name == "mysql":
        return db.execute(text("SELECT UTC_TIMESTAMP(6)")).scalar()
    return datetime.utcnow()


def now_for(project: Project) -> datetime:
    """The time a requirement is judged at: the database's clock as read when
    it was locked (lock_project), else the app clock (a plain read)."""
    return getattr(project, "_judged_at", None) or datetime.utcnow()


def is_sealed_and_open(project: Project) -> bool:
    return (
        project.tender_type == TenderType.sealed
        # Ended before its deadline (canceled, or closed outside U-Tender):
        # sealed bids stay sealed until the deadline all the same, so ending
        # a tender early is never a way to read competitors' sealed prices.
        and project.status in (ProjectStatus.open, ProjectStatus.canceled, ProjectStatus.no_award)
        and project.bid_deadline > now_for(project)
    )


# Bidding is open only while the tender is "open" AND the deadline hasn't
# passed — the instant of the deadline itself is closed, matching
# sync_expired_projects (<=) and publish (<=). Judged on the server clock;
# nothing the client sends is consulted.
def bidding_is_open(project: Project) -> bool:
    # Stage 3.15: an owner-paused requirement accepts nothing -- no offers,
    # revisions, withdrawals, attachments or questions -- until resumed.
    # Stage 3.18: nor does one an admin has suspended (moderation) -- the same
    # one rule for offers, revisions, withdrawals, confirmations and questions.
    return (
        project.status == ProjectStatus.open
        and project.paused_at is None
        and not project.is_suspended
        and project.bid_deadline > now_for(project)
    )


# SELECT ... FOR UPDATE on the tender row. Every operation that can change
# whether bids are acceptable — submit, withdraw, close, cancel, evaluate,
# award, amend — takes THIS lock first (always before any offer row, so lock
# order is the same everywhere and can't deadlock), then re-reads and checks
# the state under it. That makes "bid arrives as the owner closes" and "two
# awards at once" resolve to one clear winner instead of both passing a stale
# check. populate_existing so an already-loaded copy is refreshed, not reused.
# (SQLite, used by most tests, ignores FOR UPDATE; the guarantee is MySQL's.)
def lock_project(db: Session, project_id: str) -> Project | None:
    project = db.query(Project).filter(Project.id == project_id).populate_existing().with_for_update().first()
    if project is not None:
        # Judged by the database's clock, read under the lock: every app
        # server decides "before the deadline?" by the same time.
        project._judged_at = db_now(db)
    return project


# Bidding isn't cron-driven — a project's deadline passing is detected
# lazily, the first time anything reads it, and written through so the
# stored status is never stale for more than one request. Only 'open'
# projects, and unpublished (non-discarded) drafts, past their deadline ever
# move here; every other status (under_evaluation, awarded, no_award,
# canceled, expired itself) is already terminal/owner-driven, so this never
# fights a manual lifecycle action.
def sync_expired_projects(db: Session) -> None:
    now = db_now(db)
    # skip_locked: a row another request is transitioning right now (owner
    # cancel/award, say) is left alone instead of overwritten with a stale
    # closed/expired — the next read picks it up if it's still open.
    stale = (
        db.query(Project)
        .filter(
            Project.status.in_([ProjectStatus.open, ProjectStatus.draft]),
            Project.bid_deadline <= now,
            Project.discarded_at.is_(None),
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    if not stale:
        # End the transaction even when nothing expired: under MySQL's
        # REPEATABLE READ the FOR UPDATE scan above keeps its locks on the
        # status-index entries it read (open requirements whose deadline
        # hasn't passed) until commit. Held for the rest of the request, they
        # deadlocked against another request that already held a
        # requirement's row lock and was changing its status (cancel vs close
        # externally, at once). Callers run this first, with nothing pending.
        db.commit()
        return
    for project in stale:
        if project.status == ProjectStatus.draft:
            # Stage 3.11: a draft whose offer deadline passed before it was
            # published has expired. It was never published, so it stays
            # private (providers can't open an expired tender they didn't
            # bid on) and is now read-only.
            project.status = ProjectStatus.expired
            continue
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
        # Offers stopped at the deadline (Stage 3.15), paused or not.
        project.closed_at = project.bid_deadline
        project.paused_at = None
    db.commit()


def publish(db: Session, project: Project, actor_id: str) -> None:
    """Stage 3.14: the one transition from draft to published, used by every
    path that publishes. The caller holds the row lock (lock_project), so the
    checks below and the change are one step: a second publish finds it no
    longer a draft, and nothing becomes visible to providers until the commit
    that makes it open -- with its deadline, its server-recorded
    publication time and its audit entry -- succeeds as a whole."""
    from fastapi import HTTPException

    from app.services import requirement_quality
    from app.services.audit import log_action

    if project.status != ProjectStatus.draft or project.discarded_at is not None:
        raise HTTPException(status_code=400, detail="Only a draft project can be published.")
    now = db_now(db)
    if project.bid_deadline is None or project.bid_deadline <= now:
        raise HTTPException(status_code=400, detail="Set a bid deadline in the future before publishing.")
    requirement_quality.assert_publishable(db, project)  # Stage 3.12, authoritative
    project.status = ProjectStatus.open
    project.published_at = now.replace(microsecond=0)
    # log_action commits: the status, the timestamp and the audit entry land together.
    log_action(db, actor_id=actor_id, action="project.publish", target_type="project", target_id=project.id, previous_value="draft", new_value="open")
    _announce(db, project)


def _announce(db: Session, project: Project) -> None:
    """After the publication is committed -- never before, so no one is told
    about a requirement that didn't go live -- tell the providers it is for.
    Best-effort: a failed notification never undoes a publication."""
    import logging

    from app.models.enums import NotificationType
    from app.services.email import notify_provider_new_requirement
    from app.services.eligibility import matching_providers
    from app.services.notify import notify
    from app.services.team import side_users

    try:
        area = ", ".join(x for x in (project.area, (project.governorate or "").replace("_", " ").title()) if x) or project.address
        deadline = project.bid_deadline.strftime("%d %b %Y %H:%M UTC")
        details = {"project_title": project.title, "trade": project.trade or "", "area": area, "deadline": deadline}
        for profile in matching_providers(db, project):
            # Every member of a provider organization; just the person otherwise.
            for person in side_users(db, profile.organization_id, profile.user_id):
                notify(db, person, NotificationType.new_requirement, link=f"/service-provider/projects/{project.id}/offer", **details)
                notify_provider_new_requirement(person.email, person.language.value, project_id=project.id, **details)
    except Exception:
        db.rollback()
        logging.getLogger("notify").exception("new-requirement notifications failed for %s", project.id)


def interested_providers(db: Session, project: Project) -> list:
    """Providers who were told about this requirement (a new-opportunity
    notification), asked about it, or are preparing an offer draft on it
    (Stage 5.2), but have no submitted offer -- everyone who may be preparing
    one. Bidders are told through their offer instead."""
    from app.models.clarification import Clarification
    from app.models.enums import NotificationType, UserRole
    from app.models.notification import Notification
    from app.models.offer import Offer, tendered
    from app.models.user import User
    from app.services.team import side_users

    link = f"/service-provider/projects/{project.id}/offer"
    bidders: set[str] = set()
    for provider_id, organization_id in db.query(Offer.service_provider_id, Offer.organization_id).filter(Offer.project_id == project.id, tendered()).distinct():
        bidders.update(u.id for u in side_users(db, organization_id, provider_id))
    told = {n.user_id for n in db.query(Notification.user_id).filter(Notification.type == NotificationType.new_requirement, Notification.link == link)}
    for provider_id, organization_id in db.query(Clarification.service_provider_id, Clarification.organization_id).filter(Clarification.project_id == project.id).distinct():
        told.update(u.id for u in side_users(db, organization_id, provider_id))
    for provider_id, organization_id in db.query(Offer.service_provider_id, Offer.organization_id).filter(Offer.project_id == project.id, Offer.status == OfferStatus.draft).distinct():
        told.update(u.id for u in side_users(db, organization_id, provider_id))
    ids = told - bidders
    if not ids:
        return []
    return db.query(User).filter(User.id.in_(ids), User.role == UserRole.service_provider).order_by(User.id).all()

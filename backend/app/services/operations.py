"""Stage 9.1: the operator's picture of the marketplace -- what state it is
in and what needs attention -- read from the authoritative records with
grouped counts and short, bounded lists (oldest first), never whole tables.
Each section is computed on its own: one that fails reports itself
unavailable instead of a reassuring zero, and the others still load.
Thresholds are only the ones the platform already runs on (the hourly
deadline-reminder job, its 24-hour window); everything else is shown with
its age for the operator to judge."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.agreement import Agreement
from app.models.enums import ProjectStatus, SubscriptionStatus, VerificationStatus
from app.models.offer import Offer, tendered
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.review import ReviewReport
from app.models.service_provider import ServiceProviderProfile
from app.services.team import stakeholder_rows as _stakeholders
from app.services.tender_lifecycle import db_now, sync_expired_projects

logger = logging.getLogger(__name__)

LIST_LIMIT = 10
REMINDER_WINDOW = timedelta(hours=24)  # the deadline-reminder job's window (routers/cron.py)
REMINDER_GRACE = timedelta(hours=1)  # it is meant to run roughly hourly


def _by(db: Session, column, *where) -> dict:
    return {(k.value if hasattr(k, "value") else k): n for k, n in db.query(column, func.count()).filter(*where).group_by(column).all()}


def _accounts(db: Session, now: datetime) -> dict:
    owners = _stakeholders(OwnerProfile)
    providers = _stakeholders(ServiceProviderProfile)
    owner_status = _by(db, OwnerProfile.verification_status, owners, OwnerProfile.is_suspended.is_(False))
    provider_status = _by(db, ServiceProviderProfile.verification_status, providers, ServiceProviderProfile.is_suspended.is_(False))
    paying = ServiceProviderProfile.subscription_status.in_([SubscriptionStatus.active, SubscriptionStatus.trialing])
    approved = (providers, ServiceProviderProfile.is_suspended.is_(False), ServiceProviderProfile.verification_status == VerificationStatus.approved)
    return {
        "owners": {
            "total": db.query(func.count()).select_from(OwnerProfile).filter(owners).scalar(),
            "active": owner_status.get("approved", 0),
            "awaiting_review": owner_status.get("pending_review", 0),
            "changes_requested": owner_status.get("changes_requested", 0),
            "suspended": db.query(func.count()).select_from(OwnerProfile).filter(owners, OwnerProfile.is_suspended.is_(True)).scalar(),
        },
        "providers": {
            "total": db.query(func.count()).select_from(ServiceProviderProfile).filter(providers).scalar(),
            # the marketplace gate (ServiceProviderProfile.is_verified_active), as a count
            "can_bid": db.query(func.count()).select_from(ServiceProviderProfile).filter(
                *approved, or_(paying, ServiceProviderProfile.payment_override_active.is_(True))).scalar(),
            "approved_without_payment": db.query(func.count()).select_from(ServiceProviderProfile).filter(
                *approved, ~paying, ServiceProviderProfile.payment_override_active.is_(False)).scalar(),
            "payment_failed": db.query(func.count()).select_from(ServiceProviderProfile).filter(
                *approved, ServiceProviderProfile.subscription_status.in_([SubscriptionStatus.past_due, SubscriptionStatus.failed]),
                ServiceProviderProfile.payment_override_active.is_(False)).scalar(),
            "awaiting_review": provider_status.get("pending_review", 0),
            "changes_requested": provider_status.get("changes_requested", 0),
            "suspended": db.query(func.count()).select_from(ServiceProviderProfile).filter(providers, ServiceProviderProfile.is_suspended.is_(True)).scalar(),
        },
    }


def _requirements(db: Session, now: datetime) -> dict:
    live = (Project.discarded_at.is_(None),)
    status = _by(db, Project.status, *live)
    offered = db.query(Offer.project_id).filter(tendered(), Offer.status != "withdrawn").distinct()
    open_ = (Project.status == ProjectStatus.open, Project.is_suspended.is_(False))
    return {
        "by_status": {s.value: status.get(s.value, 0) for s in ProjectStatus},
        "suspended": db.query(func.count(Project.id)).filter(Project.is_suspended.is_(True), *live).scalar(),
        "open_with_offers": db.query(func.count(Project.id)).filter(*open_, Project.id.in_(offered)).scalar(),
        "open_without_offers": db.query(func.count(Project.id)).filter(*open_, Project.id.notin_(offered)).scalar(),
    }


def _offers(db: Session, now: datetime) -> dict:
    # Counts only -- no amounts, no bidder names; a sealed offer stays sealed here too.
    return {
        "by_status": _by(db, Offer.status, tendered()),
        "submitted_last_7_days": db.query(func.count(Offer.id)).filter(tendered(), Offer.submitted_at >= now - timedelta(days=7)).scalar(),
        "on_open_requirements": db.query(func.count(Offer.id)).join(Project, Project.id == Offer.project_id).filter(
            tendered(), Offer.status != "withdrawn", Project.status == ProjectStatus.open).scalar(),
    }


def _transactions(db: Session, now: datetime) -> dict:
    status = _by(db, Agreement.status)
    return {
        "by_status": {s: status.get(s, 0) for s in ("preparing", "active", "completed", "terminated")},
        "on_hold": db.query(func.count(Agreement.id)).filter(Agreement.status == "active", Agreement.on_hold_at.isnot(None)).scalar(),
        "completion_awaiting_owner": db.query(func.count(Agreement.id)).filter(
            Agreement.status == "active", Agreement.completion_status == "submitted").scalar(),
        "awarded_last_7_days": db.query(func.count(Agreement.id)).filter(Agreement.created_at >= now - timedelta(days=7)).scalar(),
    }


def _items(rows, since_index: int = 2) -> list[dict]:
    return [{"id": r[0], "title": r[1], "since": r[since_index]} for r in rows]


def _attention(db: Session, now: datetime) -> list[dict]:
    """What may need a person now -- each a count and its oldest few, with
    `link` the admin page (a trailing "/" takes an item's id)."""
    out = []

    def add(kind, query, order, link):
        count = query.count()
        if count:
            out.append({"kind": kind, "count": count, "link": link, "items": _items(query.order_by(order, Project.id).limit(LIST_LIMIT).all())})

    offered = db.query(Offer.project_id).filter(tendered(), Offer.status != "withdrawn").distinct()
    add("open_without_offers_closing_24h",
        db.query(Project.id, Project.title, Project.bid_deadline).filter(
            Project.status == ProjectStatus.open, Project.is_suspended.is_(False), Project.id.notin_(offered),
            Project.bid_deadline <= now + REMINDER_WINDOW),
        Project.bid_deadline.asc(), "/admin/projects/")
    add("open_without_offers",
        db.query(Project.id, Project.title, Project.published_at).filter(
            Project.status == ProjectStatus.open, Project.is_suspended.is_(False), Project.id.notin_(offered)),
        Project.published_at.asc(), "/admin/projects/")
    add("awaiting_owner_decision",
        db.query(Project.id, Project.title, Project.closed_at).filter(
            Project.status.in_([ProjectStatus.closed, ProjectStatus.under_evaluation]), Project.is_suspended.is_(False)),
        Project.closed_at.asc(), "/admin/projects/")
    add("completion_awaiting_owner",
        db.query(Project.id, Project.title, Agreement.completion_submitted_at).join(Agreement, Agreement.project_id == Project.id).filter(
            Agreement.status == "active", Agreement.completion_status == "submitted"),
        Agreement.completion_submitted_at.asc(), "/admin/projects/")
    add("transactions_on_hold",
        db.query(Project.id, Project.title, Agreement.on_hold_at).join(Agreement, Agreement.project_id == Project.id).filter(
            Agreement.status == "active", Agreement.on_hold_at.isnot(None)),
        Agreement.on_hold_at.asc(), "/admin/projects/")
    add("agreements_not_in_force",
        db.query(Project.id, Project.title, Agreement.created_at).join(Agreement, Agreement.project_id == Project.id).filter(
            Agreement.status == "preparing"),
        Agreement.created_at.asc(), "/admin/projects/")
    for model, kind, link in ((ServiceProviderProfile, "providers_awaiting_review", "/admin/service-providers/"),
                              (OwnerProfile, "owners_awaiting_review", "/admin/owners/")):
        q = db.query(model.user_id, model.user_id, model.verification_submitted_at).filter(
            _stakeholders(model), model.is_suspended.is_(False), model.verification_status == VerificationStatus.pending_review)
        count = q.count()
        if count:
            out.append({"kind": kind, "count": count, "link": link,
                        "items": [{"id": r[0], "title": None, "since": r[2]} for r in q.order_by(model.verification_submitted_at.asc(), model.user_id).limit(LIST_LIMIT)]})
    failed = db.query(ServiceProviderProfile.user_id, ServiceProviderProfile.company_name, ServiceProviderProfile.subscription_current_period_end).filter(
        _stakeholders(ServiceProviderProfile), ServiceProviderProfile.is_suspended.is_(False),
        ServiceProviderProfile.verification_status == VerificationStatus.approved,
        ServiceProviderProfile.subscription_status.in_([SubscriptionStatus.past_due, SubscriptionStatus.failed]),
        ServiceProviderProfile.payment_override_active.is_(False))
    failed_count = failed.count()
    if failed_count:
        out.append({"kind": "provider_payment_failed", "count": failed_count, "link": "/admin/service-providers/",
                    "items": _items(failed.order_by(ServiceProviderProfile.user_id).limit(LIST_LIMIT).all())})
    reports = db.query(func.count(ReviewReport.id)).filter(ReviewReport.status == "open").scalar()
    if reports:
        oldest = db.query(func.min(ReviewReport.created_at)).filter(ReviewReport.status == "open").scalar()
        out.append({"kind": "open_review_reports", "count": reports, "link": "/admin/review-reports", "items": [{"id": None, "title": None, "since": oldest}]})
    return out


def _background(db: Session, now: datetime) -> dict:
    """The deadline-reminder job is called by an external scheduler and keeps
    no run log, so its health is read from what it should have done: a
    reminder still unsent over an hour after its requirement entered the
    24-hour window means the job isn't running. Email delivery isn't
    recorded at all, so it is reported as not tracked -- never as fine."""
    due = db.query(func.count(Project.id)).filter(
        Project.status == ProjectStatus.open, Project.deadline_reminder_sent.is_(False),
        Project.bid_deadline > now, Project.bid_deadline <= now + REMINDER_WINDOW - REMINDER_GRACE,
        Project.published_at <= now - REMINDER_GRACE,
    ).scalar()
    in_window = db.query(func.count(Project.id)).filter(
        Project.status == ProjectStatus.open, Project.bid_deadline > now, Project.bid_deadline <= now + REMINDER_WINDOW).scalar()
    return {
        "deadline_reminders": "overdue" if due else ("ok" if in_window else "not_determinable"),
        "deadline_reminders_overdue": due,
        "email_delivery": "not_tracked",
    }


SECTIONS = (("accounts", _accounts), ("requirements", _requirements), ("offers", _offers),
            ("transactions", _transactions), ("attention", _attention), ("background", _background))


def overview(db: Session) -> dict:
    # Requirements past their deadline are closed/expired on read (Stage 3);
    # do it first so none is counted as still open.
    sync_expired_projects(db)
    now = db_now(db)
    out: dict = {"as_of": now}
    for name, compute in SECTIONS:
        try:
            out[name] = {"available": True, "data": compute(db, now)}
        except Exception:  # noqa: BLE001 -- one failing section must not hide or fake the others
            db.rollback()
            logger.exception("Operations overview: section %s failed", name)
            out[name] = {"available": False, "data": None}
    return out

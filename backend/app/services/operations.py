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

from app.models.agreement import Agreement, Milestone, Variation
from app.models.enums import ProjectStatus, SubscriptionStatus, VerificationStatus
from app.models.offer import Offer, tendered
from app.models.organization import Organization
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
BACKUP_STALE_AFTER = timedelta(hours=26)  # the backup timer runs daily (deploy.sh), with slack


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
    # Stage 9.10: waiting on one of the parties -- the operator can see where, not act for them.
    add("deliverables_awaiting_owner",
        db.query(Project.id, Project.title, Milestone.delivered_at).join(Agreement, Agreement.project_id == Project.id)
        .join(Milestone, Milestone.agreement_id == Agreement.id).filter(Agreement.status == "active", Milestone.status == "delivered"),
        Milestone.delivered_at.asc(), "/admin/projects/")
    add("changes_awaiting_answer",
        db.query(Project.id, Project.title, Variation.proposed_at).join(Agreement, Agreement.project_id == Project.id)
        .join(Variation, Variation.agreement_id == Agreement.id).filter(Agreement.status == "active", Variation.status == "proposed"),
        Variation.proposed_at.asc(), "/admin/projects/")
    for model, kind, link in ((ServiceProviderProfile, "providers_awaiting_review", "/admin/service-providers/"),
                              (OwnerProfile, "owners_awaiting_review", "/admin/owners/")):
        name = model.company_name if model is ServiceProviderProfile else Organization.legal_name
        q = db.query(model.user_id, name, model.verification_submitted_at).outerjoin(Organization, Organization.id == model.organization_id).filter(
            _stakeholders(model), model.is_suspended.is_(False), model.verification_status == VerificationStatus.pending_review)
        count = q.count()
        if count:
            out.append({"kind": kind, "count": count, "link": link,
                        "items": [{"id": r[0], "title": r[1], "since": r[2]} for r in q.order_by(model.verification_submitted_at.asc(), model.user_id).limit(LIST_LIMIT)]})
    failed = db.query(ServiceProviderProfile.user_id, ServiceProviderProfile.company_name, ServiceProviderProfile.subscription_current_period_end).filter(
        _stakeholders(ServiceProviderProfile), ServiceProviderProfile.is_suspended.is_(False),
        ServiceProviderProfile.verification_status == VerificationStatus.approved,
        ServiceProviderProfile.subscription_status.in_([SubscriptionStatus.past_due, SubscriptionStatus.failed]),
        ServiceProviderProfile.payment_override_active.is_(False))
    failed_count = failed.count()
    if failed_count:
        out.append({"kind": "provider_payment_failed", "count": failed_count, "link": "/admin/service-providers/",
                    "items": _items(failed.order_by(ServiceProviderProfile.user_id).limit(LIST_LIMIT).all())})
    # Stage 9.10: emails that couldn't be sent in the last day -- what and when (the business
    # action they were about is unaffected; 9.5). No link: there is nothing to retry from here.
    from app.models.email_failure import EmailFailure

    failed_mail = db.query(EmailFailure.id, EmailFailure.subject, EmailFailure.created_at).filter(EmailFailure.created_at >= now - timedelta(hours=24))
    mail_count = failed_mail.count()
    if mail_count:
        out.append({"kind": "email_failures", "count": mail_count, "link": "",
                    "items": _items(failed_mail.order_by(EmailFailure.created_at.desc(), EmailFailure.id).limit(LIST_LIMIT).all())})
    reports = db.query(func.count(ReviewReport.id)).filter(ReviewReport.status == "open").scalar()
    if reports:
        oldest = db.query(func.min(ReviewReport.created_at)).filter(ReviewReport.status == "open").scalar()
        out.append({"kind": "open_review_reports", "count": reports, "link": "/admin/review-reports", "items": [{"id": None, "title": None, "since": oldest}]})
    return out


def _backup_status(backup_dir: str | None, now: datetime) -> dict:
    """Stage 9.12: backup.sh writes last-success / last-failure into
    BACKUP_DIR. Read from there: not configured, never run, failing (the
    latest run failed), overdue (no success within a day and a bit), or
    recent -- a recent backup isn't proof it restores, so never "healthy"."""
    import json
    import os

    def read(name):
        try:
            with open(os.path.join(backup_dir, name)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def when(record):
        try:
            return datetime.fromisoformat(record["at"].replace("Z", "+00:00")).replace(tzinfo=None)
        except (TypeError, KeyError, ValueError, AttributeError):
            return None

    if not backup_dir:
        return {"backup": "not_configured", "last_backup_at": None, "backup_failed_step": None}
    success, failure = read("last-success"), read("last-failure")
    success_at, failure_at = when(success), when(failure)
    if failure_at and (not success_at or failure_at >= success_at):
        status = "failing"
    elif not success_at:
        status = "never_run"
    elif now - success_at > BACKUP_STALE_AFTER:
        status = "overdue"
    else:
        status = "recent"
    return {"backup": status, "last_backup_at": success_at,
            "backup_failed_step": failure.get("step") if status == "failing" and isinstance(failure, dict) else None}


def _background(db: Session, now: datetime) -> dict:
    """The deadline-reminder job is called by an external scheduler and keeps
    no run log, so its health is read from what it should have done: a
    reminder still unsent over an hour after its requirement entered the
    24-hour window means the job isn't running. Each failed email is recorded
    (Stage 9.5), so delivery reads failing, no failures recorded, or not
    configured -- never simply "fine"."""
    due = db.query(func.count(Project.id)).filter(
        Project.status == ProjectStatus.open, Project.deadline_reminder_sent.is_(False),
        Project.bid_deadline > now, Project.bid_deadline <= now + REMINDER_WINDOW - REMINDER_GRACE,
        Project.published_at <= now - REMINDER_GRACE,
    ).scalar()
    in_window = db.query(func.count(Project.id)).filter(
        Project.status == ProjectStatus.open, Project.bid_deadline > now, Project.bid_deadline <= now + REMINDER_WINDOW).scalar()
    # Stage 9.5: failed sends are recorded (email_failures), so delivery
    # problems show; "no failures recorded" is not a promise of delivery.
    from app.config import get_settings
    from app.models.email_failure import EmailFailure

    settings = get_settings()
    failures = db.query(func.count(EmailFailure.id)).filter(EmailFailure.created_at >= now - timedelta(hours=24)).scalar()
    if not settings.resend_api_key:
        email = "not_configured"
    else:
        email = "failing" if failures else "no_failures_recorded"
    # Stage 9.10: billing webhooks -- configured or not, and when Stripe last told us anything.
    # Nothing here can prove Stripe is delivering, so it is never called healthy.
    last_billing_event = db.query(func.max(ServiceProviderProfile.subscription_event_at)).scalar()
    return {
        "billing_webhook": "configured" if settings.stripe_webhook_secret else "not_configured",
        "last_billing_event_at": last_billing_event,
        "deadline_reminders": "overdue" if due else ("ok" if in_window else "not_determinable"),
        "deadline_reminders_overdue": due,
        "email_delivery": email,
        "email_failures_24h": failures,
        **_backup_status(settings.backup_dir, now),
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


# ---------- Stage 9.9: activity over a period, funnels, subscriptions ----------

PERIODS = ("today", "7d", "30d", "month", "all")

DEFINITIONS = {
    "new_accounts": "People who signed up in the period (owner and provider accounts; admins excluded).",
    "requirements_published": "Requirements first published in the period (an amendment is not a new requirement).",
    "offers_submitted": "Offers first submitted in the period (a revision is not a new offer; drafts never count).",
    "awards": "Awards made in the period (one per requirement).",
    "transactions_completed": "Transactions whose completion the owner accepted in the period (Stage 7.11) -- not merely awarded.",
    "reviews": "Reviews written in the period, either direction, excluding any an admin hid.",
    "active_people": "Non-admin people who did anything recorded on the audit trail in the period.",
    "returning_people": "Active people whose account existed before the period began.",
    "requirement_funnel": "Of the requirements published in the period: how many received at least one offer, were awarded, were completed, or ended without an award.",
    "provider_funnel": "Of the provider stakeholders (organisations or individuals) registered in the period: verified, able to bid now, and submitted at least one offer.",
    "subscriptions": "Provider stakeholders by their current subscription state (Stripe, 9.6) -- now, not for the period. Subscription money is never mixed with tender or transaction values.",
}


def period_start(now: datetime, period: str) -> datetime | None:
    """UTC boundaries from the server's clock: today from midnight, this
    month from the 1st, 7d/30d rolling, all time unbounded."""
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period in ("7d", "30d"):
        return now - timedelta(days=7 if period == "7d" else 30)
    return None


def metrics(db: Session, period: str) -> dict:
    from app.models.audit_log import AuditLog
    from app.models.award_record import AwardRecord
    from app.models.enums import UserRole
    from app.models.review import Review
    from app.models.user import User

    sync_expired_projects(db)
    now = db_now(db)
    since = period_start(now, period)

    def within(column):
        return (column >= since,) if since else (column.isnot(None),)

    out: dict = {"period": period, "since": since, "as_of": now, "definitions": DEFINITIONS}

    def section(name, compute):
        try:
            out[name] = {"available": True, "data": compute()}
        except Exception:  # noqa: BLE001 -- a failing section says so; the others still load
            db.rollback()
            logger.exception("Metrics: section %s failed", name)
            out[name] = {"available": False, "data": None}

    def activity():
        people = (User.role != UserRole.admin,)
        active = db.query(AuditLog.actor_id).join(User, User.id == AuditLog.actor_id).filter(*within(AuditLog.created_at), *people).distinct()
        return {
            "new_accounts": db.query(func.count(User.id)).filter(*within(User.created_at), *people).scalar(),
            "requirements_published": db.query(func.count(Project.id)).filter(*within(Project.published_at)).scalar(),
            "offers_submitted": db.query(func.count(Offer.id)).filter(tendered(), *within(Offer.submitted_at)).scalar(),
            "awards": db.query(func.count(AwardRecord.id)).filter(*within(AwardRecord.created_at)).scalar(),
            "transactions_completed": db.query(func.count(Agreement.id)).filter(Agreement.status == "completed", *within(Agreement.completed_at)).scalar(),
            "reviews": db.query(func.count(Review.id)).filter(Review.hidden_at.is_(None), *within(Review.created_at)).scalar(),
            "active_people": active.count(),
            "returning_people": (db.query(func.count(User.id)).filter(User.id.in_(active), User.created_at < since).scalar() if since else None),
        }

    def requirement_funnel():
        cohort = db.query(Project.id).filter(*within(Project.published_at))
        offered = db.query(Offer.project_id).filter(tendered()).distinct()
        return {
            "published": cohort.count(),
            "received_offers": cohort.filter(Project.id.in_(offered)).count(),
            "awarded": db.query(func.count(AwardRecord.id)).filter(AwardRecord.project_id.in_(cohort)).scalar(),
            "completed": db.query(func.count(Agreement.id)).filter(Agreement.project_id.in_(cohort), Agreement.status == "completed").scalar(),
            "ended_without_award": cohort.filter(Project.status.in_([ProjectStatus.no_award, ProjectStatus.canceled, ProjectStatus.expired])).count(),
        }

    def provider_funnel():
        sp = ServiceProviderProfile
        cohort = db.query(sp.user_id).filter(_stakeholders(sp), *within(sp.created_at))
        paying = sp.subscription_status.in_([SubscriptionStatus.active, SubscriptionStatus.trialing])
        approved = cohort.filter(sp.verification_status == VerificationStatus.approved, sp.is_suspended.is_(False))
        return {
            "registered": cohort.count(),
            "verified": approved.count(),
            "able_to_bid": approved.filter(or_(paying, sp.payment_override_active.is_(True))).count(),
            "submitted_an_offer": cohort.filter(sp.user_id.in_(db.query(Offer.service_provider_id).filter(tendered()))).count(),
        }

    def subscriptions():
        sp = ServiceProviderProfile
        base = (_stakeholders(sp),)
        by = _by(db, sp.subscription_status, *base)
        return {
            "paying": by.get("active", 0) + by.get("trialing", 0),
            "override_only": db.query(func.count(sp.user_id)).filter(*base, sp.payment_override_active.is_(True),
                                                                    or_(sp.subscription_status.is_(None), sp.subscription_status.notin_([SubscriptionStatus.active, SubscriptionStatus.trialing]))).scalar(),
            "past_due": by.get("past_due", 0) + by.get("failed", 0),
            "cancelled_or_expired": by.get("canceled", 0) + by.get("expired", 0),
            "never_subscribed": by.get(None, 0) + by.get("not_started", 0) + by.get("pending", 0),
        }

    for name, compute in (("activity", activity), ("requirement_funnel", requirement_funnel),
                          ("provider_funnel", provider_funnel), ("subscriptions", subscriptions)):
        section(name, compute)
    return out

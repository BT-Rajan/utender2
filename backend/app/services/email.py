import logging

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("email")


# Every send is wrapped so a Resend/network failure never breaks the
# calling flow (a bid still gets submitted even if the notification email
# fails) — it's logged instead. Ported from src/lib/email.ts.
def _send(to: str, subject: str, html: str) -> None:
    if _deactivated(to):  # Stage 9.5: a deactivated account (9.2) gets no email about the platform
        logger.info("skipping email to deactivated account: %s", subject)
        return
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set — skipping email to %s: %s", to, subject)
        return
    try:
        import resend

        resend.api_key = settings.resend_api_key
        resend.Emails.send({"from": settings.email_from, "to": to, "subject": subject, "html": html})
    except Exception as exc:
        logger.exception('failed to send "%s" to %s', subject, to)
        _record_failure(to, subject, exc)


def _deactivated(to: str) -> bool:
    """Looked up in a session of its own: the caller's request is never touched."""
    from app import db as db_module
    from app.models.user import User

    try:
        with db_module.SessionLocal() as s:
            return s.query(User.id).filter(User.email == to.strip().lower(), User.deactivated_at.isnot(None)).first() is not None
    except Exception:  # noqa: BLE001 -- a lookup failure never blocks a send
        logger.exception("could not check the recipient's account state")
        return False


def _record_failure(to: str, subject: str, exc: Exception) -> None:
    """Stage 9.5: keep a durable trace of a failed send for the operator (9.1
    overview), in a session of its own; never raises."""
    from app import db as db_module
    from app.models.email_failure import EmailFailure

    try:
        with db_module.SessionLocal() as s:
            s.add(EmailFailure(recipient=to[:255], subject=subject[:255], error=f"{type(exc).__name__}: {exc}"[:2000]))
            s.commit()
    except Exception:  # noqa: BLE001
        logger.exception("could not record the email failure")


def notify_owner_new_offer(
    owner_email: str, project_title: str, project_id: str, service_provider_name: str, amount: float, sealed: bool = False
) -> None:
    # Sealed-and-open (spec §19-21, D-001): the API already redacts bidder
    # identity and amount from the owner until close (see owner.py's
    # list_offers) — the email notification can't be the channel that
    # leaks the same information out the side.
    body = (
        f"<p>You received a new sealed offer on <strong>{project_title}</strong>. "
        f"Bidder identity and amount stay hidden until you close bidding.</p>"
        if sealed
        else f"<p><strong>{service_provider_name}</strong> submitted an offer of {settings.marketplace_currency} {amount:,.3f} on <strong>{project_title}</strong>.</p>"
    )
    _send(
        owner_email,
        f"New offer on {project_title}",
        f"{body}" f'<p><a href="{settings.app_url}/owner/projects/{project_id}">Review offers</a></p>',
    )


def notify_service_provider_offer_decision(service_provider_email: str, project_title: str, approved: bool) -> None:
    if approved:
        subject = f"Your offer was approved — {project_title}"
        body = f"<p>Good news — your offer on <strong>{project_title}</strong> was approved.</p>"
    else:
        subject = f"Update on your offer for {project_title}"
        body = f"<p><strong>{project_title}</strong> was awarded to a successful bidder. Best wishes for your future endeavours.</p>"

    _send(service_provider_email, subject, f'{body}<p><a href="{settings.app_url}/service-provider/feed">View open projects</a></p>')


def notify_verify_email(to_email: str, token: str) -> None:
    link = f"{settings.app_url}/verify-email?token={token}"
    _send(
        to_email,
        "Verify your U-Tender email address",
        f"<p>Confirm this is your email address to finish setting up your account.</p>"
        f'<p><a href="{link}">Verify email</a></p>'
        f"<p>This link expires in 24 hours.</p>",
    )


def notify_password_reset(to_email: str, token: str) -> None:
    link = f"{settings.app_url}/reset-password?token={token}"
    _send(
        to_email,
        "Reset your U-Tender password",
        f"<p>We received a request to reset your password.</p>"
        f'<p><a href="{link}">Reset password</a></p>'
        f"<p>This link expires in 1 hour. If you didn't request this, you can ignore this email.</p>",
    )


def notify_owner_new_clarification(owner_email: str, project_title: str, project_id: str) -> None:
    _send(
        owner_email,
        f"New question on {project_title}",
        f"<p>A service provider asked a question about <strong>{project_title}</strong>.</p>"
        f'<p><a href="{settings.app_url}/owner/projects/{project_id}">Answer it</a></p>',
    )


def notify_clarification_answered(service_provider_email: str, project_title: str, project_id: str) -> None:
    _send(
        service_provider_email,
        f"Your question was answered — {project_title}",
        f"<p>The owner of <strong>{project_title}</strong> answered your question.</p>"
        f'<p><a href="{settings.app_url}/service-provider/projects/{project_id}/offer">View the answer</a></p>',
    )


def notify_service_provider_tender_amended(service_provider_email: str, project_title: str, project_id: str, summary: str) -> None:
    _send(
        service_provider_email,
        f"Update to {project_title}",
        f"<p><strong>{project_title}</strong> was updated: {summary}</p>"
        f'<p><a href="{settings.app_url}/service-provider/projects/{project_id}/offer">Review the changes</a></p>',
    )


def notify_owner_deadline_approaching(owner_email: str, project_title: str, project_id: str, offer_count: int) -> None:
    plural = "" if offer_count == 1 else "s"
    _send(
        owner_email,
        f"Bidding closes soon — {project_title}",
        f"<p><strong>{project_title}</strong> stops accepting offers in less than 24 hours. "
        f"You currently have {offer_count} offer{plural}.</p>"
        f'<p><a href="{settings.app_url}/owner/projects/{project_id}">Review offers</a></p>',
    )


def notify_organization_invitation(to_email: str, organization_name: str, invited_by: str, token: str) -> None:
    link = f"{settings.app_url}/invite/{token}"
    _send(
        to_email,
        f"{invited_by} invited you to act for {organization_name} on U-Tender",
        f"<p><strong>{invited_by}</strong> invited you to join <strong>{organization_name}</strong> on U-Tender, "
        f"so you can work on its requirements and offers with your colleagues.</p>"
        f'<p><a href="{link}">Accept the invitation</a> (sign up first if you don\'t have an account).</p>'
        f"<p dir=\"rtl\"><strong>{invited_by}</strong> دعاك للانضمام إلى <strong>{organization_name}</strong> على U-Tender. "
        f'<a href="{link}">اقبل الدعوة</a>.</p>',
    )


def notify_provider_new_requirement(
    to_email: str, language: str, project_title: str, project_id: str, trade: str, area: str, deadline: str
) -> None:
    """Stage 3.14: a newly published requirement the provider is suited to
    (the same audience as the in-app notification), in their language."""
    link = f"{settings.app_url}/service-provider/projects/{project_id}/offer"
    if language == "ar":
        subject = f"فرصة جديدة على U-Tender: {project_title}"
        html = (
            f'<div dir="rtl"><p>نُشر طلب جديد لأعمال <strong>{trade}</strong> في {area}: <strong>{project_title}</strong>.</p>'
            f"<p>أنت تستوفي شروطه، والعروض مفتوحة حتى {deadline}.</p>"
            f'<p><a href="{link}">اطّلع على الطلب وقدّم عرضك</a></p></div>'
        )
    else:
        subject = f"New opportunity on U-Tender: {project_title}"
        html = (
            f"<p>A new <strong>{trade}</strong> requirement in {area} has been published: <strong>{project_title}</strong>.</p>"
            f"<p>You meet its conditions, and offers are open until {deadline}.</p>"
            f'<p><a href="{link}">View the requirement and send your offer</a></p>'
        )
    _send(to_email, subject, html)


def notify_provider_requirement_ended(to_email: str, language: str, project_title: str, project_id: str) -> None:
    """Stage 3.16: a requirement the provider was told about (by the
    new-opportunity email) ended before its deadline, in their language."""
    from html import escape

    title = escape(project_title)
    link = f"{settings.app_url}/service-provider/projects/{project_id}/offer"
    if language == "ar":
        subject = f"انتهى الطلب على U-Tender: {project_title}"
        html = f'<div dir="rtl"><p>أنهى المالك <strong>{title}</strong> قبل موعده النهائي، ولم يعد مفتوحًا لتلقي العروض.</p><p><a href="{link}">اطّلع على الطلب</a></p></div>'
    else:
        subject = f"Requirement ended on U-Tender: {project_title}"
        html = f'<p>The owner ended <strong>{title}</strong> before its deadline. It is no longer open for offers.</p><p><a href="{link}">View the requirement</a></p>'
    _send(to_email, subject, html)

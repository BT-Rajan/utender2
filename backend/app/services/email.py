import logging

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("email")


# Every send is wrapped so a Resend/network failure never breaks the
# calling flow (a bid still gets submitted even if the notification email
# fails) — it's logged instead. Ported from src/lib/email.ts.
def _send(to: str, subject: str, html: str) -> None:
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set — skipping email to %s: %s", to, subject)
        return
    try:
        import resend

        resend.api_key = settings.resend_api_key
        resend.Emails.send({"from": settings.email_from, "to": to, "subject": subject, "html": html})
    except Exception:
        logger.exception('failed to send "%s" to %s', subject, to)


def notify_owner_new_offer(
    owner_email: str, project_title: str, project_id: str, contractor_name: str, amount: float, sealed: bool = False
) -> None:
    # Sealed-and-open (spec §19-21, D-001): the API already redacts bidder
    # identity and amount from the owner until close (see owner.py's
    # list_offers) — the email notification can't be the channel that
    # leaks the same information out the side.
    body = (
        f"<p>You received a new sealed offer on <strong>{project_title}</strong>. "
        f"Bidder identity and amount stay hidden until you close bidding.</p>"
        if sealed
        else f"<p><strong>{contractor_name}</strong> submitted an offer of ${amount:,.2f} on <strong>{project_title}</strong>.</p>"
    )
    _send(
        owner_email,
        f"New offer on {project_title}",
        f"{body}" f'<p><a href="{settings.app_url}/owner/projects/{project_id}">Review offers</a></p>',
    )


def notify_contractor_offer_decision(contractor_email: str, project_title: str, approved: bool) -> None:
    if approved:
        subject = f"Your offer was approved — {project_title}"
        body = f"<p>Good news — your offer on <strong>{project_title}</strong> was approved.</p>"
    else:
        subject = f"Update on your offer for {project_title}"
        body = f"<p>The owner of <strong>{project_title}</strong> went with another offer this time.</p>"

    _send(contractor_email, subject, f'{body}<p><a href="{settings.app_url}/contractor/feed">View open projects</a></p>')


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


def notify_clarification_answered(contractor_email: str, project_title: str, project_id: str) -> None:
    _send(
        contractor_email,
        f"Your question was answered — {project_title}",
        f"<p>The owner of <strong>{project_title}</strong> answered your question.</p>"
        f'<p><a href="{settings.app_url}/contractor/projects/{project_id}/offer">View the answer</a></p>',
    )


def notify_contractor_tender_amended(contractor_email: str, project_title: str, project_id: str, summary: str) -> None:
    _send(
        contractor_email,
        f"Update to {project_title}",
        f"<p><strong>{project_title}</strong> was updated: {summary}</p>"
        f'<p><a href="{settings.app_url}/contractor/projects/{project_id}/offer">Review the changes</a></p>',
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

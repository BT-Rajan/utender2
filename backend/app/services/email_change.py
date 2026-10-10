"""Changing a person's sign-in email.

Self-service: they ask for a change (signed in, with their current password),
a six-digit code goes to their CURRENT address, and entering it switches the
account to the new address. The new address then has to be verified like a
fresh signup's. If they have lost the old mailbox, an admin edits the account
instead (routers.admin: PATCH /admin/users/{id}).

Security notes:
- the code is stored only as an HMAC (keyed with the server secret, salted with
  the request id) -- a bare hash of six digits could be reversed instantly;
- a request dies after MAX_ATTEMPTS wrong codes or CODE_TTL, whichever is first;
- requests are rate-limited per account (cooldown + hourly cap), and a new
  request supersedes any earlier one;
- availability of the new address is checked only at confirmation, i.e. only
  after the caller has proved control of the old mailbox, so this isn't an
  open way to probe which emails have accounts.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import verify_password
from app.config import get_settings
from app.models.email_change import EmailChangeRequest
from app.models.enums import AuthTokenType
from app.models.user import User
from app.services.audit import log_action
from app.services.auth_tokens import issue_token
from app.services.email import notify_email_change_code, notify_email_changed, notify_verify_email

settings = get_settings()

CODE_TTL = timedelta(minutes=15)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_REQUESTS_PER_HOUR = 5


def _code_hash(request_id: str, code: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"{request_id}:{code}".encode(), hashlib.sha256).hexdigest()


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'*' * max(len(local) - 1, 1)}@{domain}"


def request_change(db: Session, user: User, new_email: str, current_password: str) -> str:
    """Sends the code to the user's current address. Returns that address, masked."""
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    new_email = new_email.strip().lower()
    if new_email == user.email.strip().lower():
        raise HTTPException(status_code=400, detail="Your new email address must be different from the current one.")

    now = datetime.utcnow()
    recent = db.query(EmailChangeRequest).filter(EmailChangeRequest.user_id == user.id, EmailChangeRequest.created_at > now - timedelta(hours=1)).all()
    if len(recent) >= MAX_REQUESTS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many email change requests. Please try again later.", headers={"Retry-After": "3600"})
    newest = max((r.created_at for r in recent), default=None)
    if newest is not None and now - newest < RESEND_COOLDOWN:
        wait = int((RESEND_COOLDOWN - (now - newest)).total_seconds()) + 1
        raise HTTPException(status_code=429, detail="Please wait a minute before requesting another code.", headers={"Retry-After": str(wait)})

    # A new request supersedes any earlier one that's still open.
    db.query(EmailChangeRequest).filter(EmailChangeRequest.user_id == user.id, EmailChangeRequest.consumed_at.is_(None)).update(
        {EmailChangeRequest.consumed_at: now}, synchronize_session=False
    )
    code = f"{secrets.randbelow(10**6):06d}"
    req = EmailChangeRequest(user_id=user.id, new_email=new_email, code_hash="", expires_at=now + CODE_TTL)
    db.add(req)
    db.flush()  # assigns req.id, which salts the hash
    req.code_hash = _code_hash(req.id, code)
    db.commit()
    notify_email_change_code(user.email, new_email, code)
    return mask_email(user.email)


def confirm_change(db: Session, user: User, code: str) -> User:
    now = datetime.utcnow()
    req = (
        db.query(EmailChangeRequest)
        .filter(EmailChangeRequest.user_id == user.id, EmailChangeRequest.consumed_at.is_(None))
        .order_by(EmailChangeRequest.created_at.desc())
        .with_for_update()
        .first()
    )
    if req is None or req.expires_at <= now:
        raise HTTPException(status_code=400, detail="That code is incorrect or has expired.")
    if req.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Too many incorrect attempts. Request a new code.")
    if not hmac.compare_digest(req.code_hash, _code_hash(req.id, code.strip())):
        req.attempts += 1
        db.commit()  # the failed attempt must be recorded even though we raise
        raise HTTPException(status_code=400, detail="That code is incorrect or has expired.")

    if db.query(User.id).filter(func.lower(User.email) == req.new_email, User.id != user.id).first():
        raise HTTPException(status_code=409, detail="That email address can't be used.")
    old_email = user.email
    user.email = req.new_email
    user.email_verified = False  # they proved the old mailbox, not the new one
    req.consumed_at = now
    try:
        db.flush()
    except IntegrityError:  # someone took it between the check and now
        db.rollback()
        raise HTTPException(status_code=409, detail="That email address can't be used.")
    log_action(db, actor_id=user.id, action="account.email_changed", target_type="user", target_id=user.id, previous_value=old_email, new_value=user.email)
    db.refresh(user)
    notify_verify_email(user.email, issue_token(db, user.id, AuthTokenType.email_verify))
    notify_email_changed(old_email, user.email)
    return user

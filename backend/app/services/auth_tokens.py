import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.auth_token import AuthToken
from app.models.enums import AuthTokenType
from app.models.user import User

EMAIL_VERIFY_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(hours=1)

_TTL_BY_TYPE = {
    AuthTokenType.email_verify: EMAIL_VERIFY_TTL,
    AuthTokenType.password_reset: PASSWORD_RESET_TTL,
}


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# Returns the raw token — this is the only place it exists in plaintext.
# Callers must put it straight into an email link, never log or store it.
def issue_token(db: Session, user_id: str, token_type: AuthTokenType) -> str:
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + _TTL_BY_TYPE[token_type]
    db.add(
        AuthToken(
            user_id=user_id,
            token_hash=_hash(raw),
            type=token_type,
            email=db.get(User, user_id).email.strip().lower(),  # the link goes to the current address
            expires_at=expires_at.replace(tzinfo=None),
        )
    )
    db.commit()
    return raw


# Single-use: a valid token is marked used() the moment it's consumed, so a
# copy of a reset/verify link (email forwarded, browser history, etc.)
# can't be replayed after the flow it was issued for has completed.
def consume_token(db: Session, raw: str, token_type: AuthTokenType) -> str | None:
    row = db.query(AuthToken).filter(AuthToken.token_hash == _hash(raw), AuthToken.type == token_type).first()
    if not row or row.used_at is not None:
        return None
    if datetime.now(timezone.utc) > _aware(row.expires_at):
        return None
    # Security: a link proves control of the mailbox it was sent to, nothing
    # more -- so after an email change it must not vouch for the new address
    # (or reset the password of an account that has moved away from it).
    user = db.get(User, row.user_id)
    if user is None or row.email is None or row.email != user.email.strip().lower():
        return None
    row.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return row.user_id


def invalidate_tokens(db: Session, user_id: str) -> None:
    """Retires every unused verify/reset link of the account (not committed).
    Called whenever its email changes: links mailed to the old address must
    stop working, whoever reads that mailbox now."""
    db.query(AuthToken).filter(AuthToken.user_id == user_id, AuthToken.used_at.is_(None)).update(
        {AuthToken.used_at: datetime.now(timezone.utc).replace(tzinfo=None)}, synchronize_session=False
    )

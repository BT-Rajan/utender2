import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from jwt import PyJWTError as JWTError
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def password_fingerprint(password_hash: str) -> str:
    """Opaque marker of the password a token was issued under (HMAC of the
    stored hash, so the claim reveals nothing about it). Changing or resetting
    the password changes the hash, which silently invalidates every token
    issued before -- sessions end without needing a token store."""
    return hmac.new(settings.jwt_secret.encode(), password_hash.encode(), hashlib.sha256).hexdigest()[:32]


def _create_token(subject: str, ttl: timedelta, token_type: str, password_hash: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
        "pwv": password_fingerprint(password_hash),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, password_hash: str) -> str:
    return _create_token(user_id, timedelta(minutes=settings.jwt_access_ttl_minutes), "access", password_hash)


def create_refresh_token(user_id: str, password_hash: str) -> str:
    return _create_token(user_id, timedelta(days=settings.jwt_refresh_ttl_days), "refresh", password_hash)


@dataclass
class TokenPayload:
    user_id: str
    jti: str
    expires_at: datetime
    pwv: str | None = None


def token_matches_password(payload: "TokenPayload", password_hash: str) -> bool:
    """False for tokens issued under a previous password -- and for tokens
    with no password claim at all (issued before this check existed), which
    simply means those sessions must log in again once."""
    return payload.pwv is not None and hmac.compare_digest(payload.pwv, password_fingerprint(password_hash))


def decode_token_payload(token: str, expected_type: str) -> TokenPayload | None:
    """Full decode, used where the token's identity (jti/exp) matters —
    e.g. revoking a specific refresh token on logout. Returns None if
    invalid, expired, or the wrong token type."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], options={"require": ["exp", "sub"]})
    except JWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    sub, jti, exp = payload.get("sub"), payload.get("jti"), payload.get("exp")
    if not sub or not jti or not exp:
        return None
    return TokenPayload(
        user_id=sub, jti=jti, expires_at=datetime.fromtimestamp(exp, tz=timezone.utc), pwv=payload.get("pwv")
    )


def decode_token(token: str, expected_type: str) -> str | None:
    """Returns the user id embedded in the token, or None if invalid/expired/wrong type."""
    payload = decode_token_payload(token, expected_type)
    return payload.user_id if payload else None

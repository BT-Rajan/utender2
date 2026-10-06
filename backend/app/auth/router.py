from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token_payload,
    hash_password,
    token_matches_password,
    verify_password,
)
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models.service_provider import ServiceProviderProfile
from app.models.enums import AuthTokenType, UserRole
from app.models.owner import OwnerProfile
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LanguageUpdate,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    VerifyEmailRequest,
)
from app.schemas.user import UserOut
from app.services.auth_tokens import consume_token, issue_token
from app.services.documents import ensure_document_rows, ensure_owner_document_rows
from app.services.email import notify_password_reset, notify_verify_email
from app.services.login_throttle import login_throttle

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

ACCESS_TTL_SECONDS = settings.jwt_access_ttl_minutes * 60
REFRESH_TTL_SECONDS = settings.jwt_refresh_ttl_days * 24 * 60 * 60


def _set_auth_cookies(response: Response, user: User) -> None:
    access_token = create_access_token(user.id, user.password_hash)
    refresh_token = create_refresh_token(user.id, user.password_hash)
    # httpOnly so a browser-side XSS can't read the token; SameSite=lax is
    # enough since frontend and backend are same-site in production
    # deployments (reverse-proxied together) — see README for the local-dev
    # cross-origin case, which needs SameSite=None + secure over https.
    secure = settings.cookies_secure
    response.set_cookie(
        "access_token", access_token, httponly=True, samesite="lax", secure=secure, max_age=ACCESS_TTL_SECONDS
    )
    response.set_cookie(
        "refresh_token", refresh_token, httponly=True, samesite="lax", secure=secure, max_age=REFRESH_TTL_SECONDS
    )


def _revoke_refresh_token(db: Session, refresh_token: str | None) -> None:
    """Best-effort: marks the given refresh token's jti as revoked so it
    can never be used again via /auth/refresh, even though it's still
    cryptographically valid until it naturally expires. Silently no-ops on
    a missing/garbled/already-expired token — there's nothing meaningful to
    revoke in that case."""
    if not refresh_token:
        return
    payload = decode_token_payload(refresh_token, expected_type="refresh")
    if not payload:
        return
    # Ignore a duplicate insert (e.g. a double-submitted logout) rather
    # than erroring on it.
    if db.get(RevokedToken, payload.jti):
        return
    db.add(RevokedToken(jti=payload.jti, expires_at=payload.expires_at.replace(tzinfo=None)))
    db.commit()


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response, db: Session = Depends(get_db)):
    if payload.role not in (UserRole.owner, UserRole.service_provider):
        raise HTTPException(status_code=400, detail="Only owner or service provider accounts can self-register.")

    email = payload.email.strip().lower()

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        full_name=payload.full_name,
    )
    db.add(user)
    db.flush()  # assigns user.id without committing yet

    if payload.role == UserRole.service_provider:
        company_name = payload.company_name or payload.full_name
        db.add(ServiceProviderProfile(user_id=user.id, company_name=company_name))
        db.flush()
        ensure_document_rows(db, user.id)
    elif payload.role == UserRole.owner:
        db.add(OwnerProfile(user_id=user.id))
        db.flush()
        ensure_owner_document_rows(db, user.id)

    try:
        db.commit()
    except IntegrityError:
        # A concurrent signup with the same email landed between our check
        # above and this commit — rare, but a clean 400 beats a raw 500.
        db.rollback()
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    db.refresh(user)

    # Best-effort, non-blocking — signup still succeeds (and the user is
    # still logged in immediately below) even if the email send fails, per
    # this app's deliberate choice not to gate login on confirmation.
    token = issue_token(db, user.id, AuthTokenType.email_verify)
    notify_verify_email(user.email, token)

    _set_auth_cookies(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    client_ip = request.client.host if request.client else "unknown"

    wait = login_throttle.retry_after(client_ip, email)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(wait)},
        )

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        login_throttle.record_failure(client_ip, email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    login_throttle.record_success(client_ip, email)
    _set_auth_cookies(response, user)
    return user


@router.post("/refresh")
def refresh(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token_payload(refresh_token, expected_type="refresh")
    user = db.get(User, payload.user_id) if payload else None
    if not payload or not user or not token_matches_password(payload, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    if db.get(RevokedToken, payload.jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    # Rotate: the token just used to refresh is retired immediately, so a
    # copy of it (leaked via logs, a shared machine, etc.) can't be reused
    # to mint further sessions after this point.
    db.add(RevokedToken(jti=payload.jti, expires_at=payload.expires_at.replace(tzinfo=None)))
    db.commit()

    _set_auth_cookies(response, user)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    _revoke_refresh_token(db, refresh_token)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/request-email-verification")
def request_email_verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.email_verified:
        return {"ok": True, "already_verified": True}
    token = issue_token(db, user.id, AuthTokenType.email_verify)
    notify_verify_email(user.email, token)
    return {"ok": True}


@router.post("/verify-email", response_model=UserOut)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    user_id = consume_token(db, payload.token, AuthTokenType.email_verify)
    if not user_id:
        raise HTTPException(status_code=400, detail="This verification link is invalid or has expired.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="This verification link is invalid or has expired.")
    user.email_verified = True
    db.commit()
    db.refresh(user)
    return user


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Always returns the same response whether or not the email exists —
    # otherwise this endpoint becomes an account-enumeration oracle.
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        token = issue_token(db, user.id, AuthTokenType.password_reset)
        notify_password_reset(user.email, token)
    return {"ok": True, "detail": "If an account with that email exists, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user_id = consume_token(db, payload.token, AuthTokenType.password_reset)
    if not user_id:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    # The new hash ends every other session; re-issue this one so the person
    # who just changed their password isn't logged out of the tab they used.
    _set_auth_cookies(response, user)
    return {"ok": True}


@router.patch("/language", response_model=UserOut)
def update_language(payload: LanguageUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.language = payload.language
    db.commit()
    db.refresh(user)
    return user

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.security import decode_token_payload, token_matches_password
from app.db import get_db
from app.models.contractor import ContractorProfile
from app.models.enums import UserRole
from app.models.owner import OwnerProfile
from app.models.user import User


# Mirrors src/middleware.ts's first check: is there a valid session at all.
# Reads the access token from an httpOnly cookie set at login, same as the
# original app relied on Supabase's auth cookie rather than a header token
# the frontend has to manage itself.
def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = decode_token_payload(access_token, expected_type="access")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    # Access tokens aren't checked against the revocation table here — only
    # the long-lived refresh token is (see /auth/refresh, /auth/logout).
    # Access tokens are short-lived (JWT_ACCESS_TTL_MINUTES, 30min default)
    # by design specifically so this per-request check can skip a DB hit;
    # logout closes the loop within one access-token lifetime at most.

    user = db.get(User, token.user_id)
    # A token issued before the user's last password change/reset is dead.
    if not user or not token_matches_password(token, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return user


# Mirrors middleware.ts's second check: does the caller's role match the
# route they're hitting (e.g. only 'admin' may reach /admin/*).
def require_role(*roles: UserRole):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _check


require_admin = require_role(UserRole.admin)
require_owner = require_role(UserRole.owner)
require_contractor = require_role(UserRole.contractor)


# Mirrors middleware.ts's contractor-specific third check: verification and
# suspension state must be re-derived on every request, not just at login,
# since an admin can flip either at any time. This is the *verification*
# gate alone — enough to browse the feed and manage one's own profile, but
# not enough to see drawings or bid (see require_marketplace_active_contractor
# below for the P0 rule that adds the payment gate on top of this one).
def require_approved_contractor(user: User = Depends(require_contractor), db: Session = Depends(get_db)) -> User:
    profile = db.get(ContractorProfile, user.id)
    if not profile or profile.verification_status.value != "approved" or profile.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not_approved",  # frontend redirects to /contractor/status on this code
        )
    return user


# THE P0 gate (spec checklist "docs approved but payment absent" /
# decision D-002/D-003): full marketplace participation — viewing a
# project's drawings, downloading them, and submitting or revising a bid —
# requires BOTH an approved verification AND active payment, where "active
# payment" is a real Stripe subscription OR an admin-granted, audited
# PaymentOverride. ContractorProfile.is_verified_active is the single
# source of truth for this; never re-derive the check inline at a call
# site (that's exactly how the pre-PASS-5 code drifted: submit_offer used
# to check is_subscribed alone, which silently ignored payment_override_active).
def require_marketplace_active_contractor(user: User = Depends(require_contractor), db: Session = Depends(get_db)) -> User:
    profile = db.get(ContractorProfile, user.id)
    if not profile or not profile.is_verified_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="payment_required",  # frontend redirects to /contractor/subscribe on this code
        )
    return user


def get_contractor_profile(user: User, db: Session) -> ContractorProfile:
    profile = db.get(ContractorProfile, user.id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor profile not found")
    return profile


# Owner-side mirror of require_approved_contractor: an owner must be
# document-verified and not suspended before posting or managing a
# project. Re-derived every request, same reasoning as the contractor
# gate — an admin can flip either flag at any time.
def require_verified_owner(user: User = Depends(require_owner), db: Session = Depends(get_db)) -> User:
    profile = db.get(OwnerProfile, user.id)
    if not profile or not profile.is_verified_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not_approved",  # frontend redirects to /owner/status on this code
        )
    return user


def get_owner_profile(user: User, db: Session) -> OwnerProfile:
    profile = db.get(OwnerProfile, user.id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner profile not found")
    return profile

"""Accepting an organization invitation needs a verified email, so tests that
set up colleagues joining an organization mark those accounts verified (as
following the emailed verification link would)."""
from app import db as app_db
from app.models.user import User


def verify_email(email: str) -> None:
    session = app_db.SessionLocal()  # reassigned per test by conftest, so read at call time
    try:
        user = session.query(User).filter(User.email == email.strip().lower()).one()
        user.email_verified = True
        session.commit()
    finally:
        session.close()

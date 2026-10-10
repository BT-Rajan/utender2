from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# A revoked refresh token's jti, so logout actually invalidates that
# session instead of just clearing the browser's cookies — a stateless JWT
# is otherwise still valid (and usable via /auth/refresh) until it expires
# on its own, even after "logout". Rows past their own expiry are inert
# (decode_token already rejects an expired token before this table is even
# consulted) and are pruned by services.token_cleanup (hourly cron + opportunistically on logout).
class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid
from app.models.enums import AuthTokenType


# Only the SHA-256 hash of the raw token is ever stored — a DB read/leak
# does not hand out a usable email-verify or password-reset link, the same
# way password_hash never stores the plaintext password.
class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    type: Mapped[AuthTokenType] = mapped_column(Enum(AuthTokenType, native_enum=True), nullable=False)
    # Security: the address the link was mailed to. A link proves control of
    # that mailbox only, so it is refused once the account's email differs.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# A pending change of a person's sign-in email. A short numeric code is sent to
# their CURRENT address; entering it proves they still control it. Six digits
# are guessable, so the code is stored only as a keyed hash (see
# services.email_change) and the request dies after a few wrong attempts or
# a short time, whichever comes first.
class EmailChangeRequest(Base):
    __tablename__ = "email_change_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    new_email: Mapped[str] = mapped_column(String(255), nullable=False)  # lower-case
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # used, or superseded by a newer request
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

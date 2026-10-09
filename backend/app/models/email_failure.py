from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


class EmailFailure(Base):
    """Stage 9.5: an email the platform tried to send and couldn't -- so an
    operator can see delivery is failing instead of assuming it works. The
    business action it was about is unaffected (emails are best-effort)."""
    __tablename__ = "email_failures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)

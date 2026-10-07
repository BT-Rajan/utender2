from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# Stage 6.11: the owner side's own evaluation notes -- private observations
# while reviewing offers, on the requirement or on one offer. Read by the
# requirement's owner side only (its organization's members, or the
# individual owner); never by providers, other owners or the public. Edited
# or removed by their author only; never scored, ranked or interpreted.
class EvaluationNote(Base):
    __tablename__ = "evaluation_notes"
    # A retried submission (same author, same client token) is one note.
    __table_args__ = (UniqueConstraint("author_id", "client_token", name="uq_evaluation_note_client_token"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    # NULL: a note on the requirement as a whole.
    offer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("offers.id", ondelete="CASCADE"), nullable=True, index=True)
    author_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    client_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

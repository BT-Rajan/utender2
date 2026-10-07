from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# Stage 6.12: offers the owner's side has shortlisted while evaluating --
# promising, not awarded. One row per shortlisted offer (several may be);
# kept apart from the offer itself, which it never changes; private to the
# requirement's owner side. Recorded against the offer's version and the
# requirement version it answered, which can't change during evaluation.
class OfferShortlist(Base):
    __tablename__ = "offer_shortlist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    offer_id: Mapped[str] = mapped_column(String(36), ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, unique=True)
    offer_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    material_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    added_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

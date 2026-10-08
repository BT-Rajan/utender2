from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # Stage 8.4: one review per completed transaction in each direction.
        UniqueConstraint("project_id", "direction", name="uq_review_project_direction"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_rating_range"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    # The transaction's two parties, from its own records (Stage 8.4): the
    # requirement's owner stakeholder (projects.owner_id) and the winning
    # provider (award_records.service_provider_id) -- whichever direction.
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    service_provider_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_provider_profiles.user_id"), nullable=False)
    # Stage 8.4: who reviewed whom -- the owner side reviewing the provider, or
    # the provider side reviewing the owner -- and the member who wrote it.
    direction: Mapped[str] = mapped_column(String(24), nullable=False, default="owner_to_provider", server_default="owner_to_provider")
    reviewer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# Batch C: how long a review stays sealed when the other side hasn't reviewed.
REVEAL_AFTER = timedelta(days=14)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        # Stage 8.4: one review per completed transaction in each direction.
        UniqueConstraint("project_id", "direction", name="uq_review_project_direction"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_rating_range"),
        # Stage 8.5: a review is one of the two directions, between two different parties.
        CheckConstraint("direction IN ('owner_to_provider', 'provider_to_owner')", name="ck_review_direction"),
        CheckConstraint("owner_id <> service_provider_id", name="ck_review_two_parties"),
        # Stage 8.9: a response is whole -- its text and its time together, or neither.
        CheckConstraint("(response IS NULL AND response_at IS NULL) OR (response IS NOT NULL AND response_at IS NOT NULL)",
                        name="ck_review_response_complete"),
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
    # Batch D: stamped in UTC by the application, not by the database server's
    # clock (NOW() is the server's local time) -- REVEAL_AFTER is measured
    # against utcnow(), so a server not on UTC would unseal reviews hours late.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow().replace(microsecond=0), server_default=func.now())
    # Batch C: reviews are double-blind -- neither side sees the other's until
    # both have reviewed, or REVEAL_AFTER has passed since this one was written.
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stage 8.9: the reviewed side's one, final response -- beside the review,
    # never changing it (rating, comment and parties stay as written).
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    responded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Stage 8.15: an admin's moderation, after a report -- the row stays (who
    # reviewed whom, what was written) but a hidden review stops being shown or
    # counted, and a hidden response stops being shown. The audit log says who.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response_hidden_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def is_revealed_now(self) -> bool:
        """Batch C: visible to the other side (both reviewed, or the sealed period passed)."""
        return self.revealed_at is not None or (self.created_at is not None and self.created_at <= datetime.utcnow() - REVEAL_AFTER)

    @property
    def reveals_on(self) -> datetime | None:
        """Batch C: when a still-sealed review is revealed at the latest."""
        return None if self.revealed_at is not None or self.created_at is None else self.created_at + REVEAL_AFTER

    @property
    def is_hidden(self) -> bool:
        return self.hidden_at is not None

    @property
    def shown_response(self) -> str | None:
        return None if self.response_hidden_at else self.response

    @property
    def shown_response_at(self) -> datetime | None:
        return None if self.response_hidden_at else self.response_at


class ReviewReport(Base):
    """Stage 8.15: a party's report of a review about it, or of the response to
    its own review -- a signal for an admin, never a change by itself. One per
    review and target; the admin keeps or hides what was reported."""
    __tablename__ = "review_reports"
    __table_args__ = (
        UniqueConstraint("review_id", "target", name="uq_review_report_target"),
        CheckConstraint("target IN ('review', 'response')", name="ck_review_report_target"),
        CheckConstraint("status IN ('open', 'kept', 'hidden')", name="ck_review_report_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    target: Mapped[str] = mapped_column(String(16), nullable=False)  # the review itself, or its response
    reporter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

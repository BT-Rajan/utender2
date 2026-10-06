from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import gen_uuid
from app.models.enums import OfferStatus


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("project_id", "service_provider_id", name="uq_project_service_provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    timeline_estimate: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OfferStatus] = mapped_column(
        Enum(OfferStatus, native_enum=True), nullable=False, default=OfferStatus.submitted
    )
    # Admin moderation flag, independent of `status` — a suspended offer is
    # hidden from the owner's evaluation view and cannot be awarded, but
    # keeps its real submitted/approved/rejected/withdrawn status intact so
    # un-suspending restores exactly what was there before.
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # This row is always the CURRENT bid. Every edit also appends an
    # OfferRevision snapshot of the pre-edit values and bumps this counter
    # (spec §29, D-009) — old values are never lost, just superseded.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    service_provider_profile = relationship("ServiceProviderProfile")


# Immutable log of every prior state of an Offer, written just before the
# current row is overwritten. revision_number matches what Offer.revision
# was AT THAT SNAPSHOT (so revision 1's row here is the bid as originally
# submitted, before the edit that created revision 2).
class OfferRevision(Base):
    __tablename__ = "offer_revisions"
    __table_args__ = (UniqueConstraint("offer_id", "revision_number", name="uq_offer_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    offer_id: Mapped[str] = mapped_column(String(36), ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    timeline_estimate: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus, native_enum=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
